"""
Copyright 2017 Pani Networks Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

"""

# The main entry point for the executable and functions to parse command line
# arguments.

import argparse
import importlib
import logging
import pkgutil
import sys

from vpcrouter.errors  import ArgsError, PluginError

from vpcrouter.vpc     import get_ec2_meta_data
from vpcrouter         import watcher
from vpcrouter.watcher import plugins


def _setup_arg_parser(plugins_class_lookup):
    """
    Configure and return the argument parser for the command line options.

    If plugins_class_lookup is provided then call the add_arguments() call back
    of the plugin classes in that dict, in order to add plugin specific
    options.

    Some parameters are required (vpc and region, for example), but we may be
    able to discover them automatically, later on. Therefore, we allow them to
    remain unset on the command line. We will have to complain about those
    parameters missing later on, if the auto discovery fails.

    Return parser and the conf-name of all the arguments that have been added.

    """

    mode_names = ", ".join("'%s'" % pn for pn in plugins_class_lookup.keys())
    parser = argparse.ArgumentParser(
                    description="VPC router: Manage routes in VPC route table")
    # General arguments
    parser.add_argument('-l', '--logfile', dest='logfile',
                        default='-',
                        help="full path name for the logfile, "
                             "or '-' for logging to stdout "
                             "(default: '-' (logging to stdout))"),
    parser.add_argument('-r', '--region', dest="region_name",
                        required=False, default=None,
                        help="the AWS region of the VPC")
    parser.add_argument('-v', '--vpc', dest="vpc_id",
                        required=False, default=None,
                        help="the ID of the VPC in which to operate")
    parser.add_argument('-m', '--mode', dest='mode', required=True,
                        help="available modes: %s" % mode_names)
    parser.add_argument('--verbose', dest="verbose", action='store_true',
                        help="produces more output")

    arglist = ["logfile", "region_name", "vpc_id", "mode", "verbose"]

    # Let each watcher plugin add its own arguments
    if plugins_class_lookup:
        for plugin_class in plugins_class_lookup.values():
            arglist.extend(plugin_class.add_arguments(parser))

    return parser, arglist


def parse_args(args_list, plugins_class_lookup=None):
    """
    Parse command line arguments and return relevant values in a dict.

    Also perform basic sanity checking on some arguments.

    If a dict of watcher plugin classes has been parsed in, callbacks into
    those classes will be used to extend the arguments with plugin-specific
    options.

    Likewise, the sanity checking will then also invoke a callback into the
    plugin, chosen by the -m (mode) option, in order to perform a sanity check
    on the plugin options.

    """
    conf = {}

    # Setting up the command line argument parser
    parser, arglist = _setup_arg_parser(plugins_class_lookup)

    args = parser.parse_args(args_list)

    for argname in arglist:
        conf[argname] = getattr(args, argname)

    # Sanity checking of arguments.
    plugin_class = plugins_class_lookup.get(conf['mode'])
    if not plugin_class:
        raise ArgsError("Unknown mode '%s'" % conf['mode'])
    try:
        # Let the watcher plugin class check its own arguments
        plugin_class.check_arguments(conf)
    except ArgsError as e:
        parser.print_help()
        raise e

    return conf


def setup_logging(conf):
    """
    Configure the logging framework.

    If run in CLI mode then all log output is simply written to stdout.

    """
    if conf['verbose']:
        level = logging.DEBUG
    else:
        level = logging.INFO

    fname = conf['logfile'] if conf['logfile'] != "-" else None

    logging.basicConfig(filename=fname, level=level,
                        format='%(asctime)s - %(levelname)-8s - '
                               '%(threadName)-11s - %(message)s')

    # Don't want to see all the messages from BOTO and watchdog
    logging.getLogger('boto').setLevel(logging.CRITICAL)
    logging.getLogger('watchdog.observers.inotify_buffer'). \
                                                setLevel(logging.CRITICAL)


def load_plugins():
    """
    Load the watcher plugins.

    Return lookup dictionary: Key is module name, value is the plugin class.

    """
    plugins_class_lookup = {}
    # Iterate over all the plugin modules we can find.
    for _, modname, ispkg in pkgutil.iter_modules(plugins.__path__):
        try:
            plugin_mod_name   = "vpcrouter.watcher.plugins.%s" % modname
            plugin_mod        = importlib.import_module(plugin_mod_name)
            plugin_class_name = modname.capitalize()
            plugin_class      = getattr(plugin_mod, plugin_class_name)
        except ImportError as e:
            raise PluginError("Cannot load '%s'" % plugin_mod_name)
        except AttributeError:
            raise PluginError("Cannot find plugin class '%s' in "
                              "plugin '%s'" %
                              (plugin_class_name, plugin_mod_name))
        except Exception as e:
            raise PluginError("Error while loading plugin '%s': %s" %
                              plugin_mod_name, str(e))

        plugins_class_lookup[modname] = plugin_class

    if not plugins_class_lookup:
        raise PluginError("Could not load any plugins")

    return plugins_class_lookup


def main():
    """
    Starting point of the executable.

    """
    # Importing all watcher plugins.
    # - Each plugin is located in the vpcrouter.watcher.plugins module.
    # - The name of the plugin file is the 'mode' of vpc-router, plus '.py'
    # - The file has to contain a class that implements the WatcherPlugin
    #   interface.
    # - The plugin class has to have the same name as the plugin itself, only
    #   capitalized.
    try:
        plugins_class_lookup = load_plugins()

        conf = parse_args(sys.argv[1:], plugins_class_lookup)
        setup_logging(conf)

        # If we are on an EC2 instance then some data is already available to
        # us. The return data items in the meta data match some of the command
        # line arguments, so we can pass this through to the parser function to
        # provide defaults for those parameters. Specifically: VPC-ID and
        # region name.
        if not conf['vpc_id'] or not conf['region_name']:
            meta_data = get_ec2_meta_data()
            if 'vpc_id' not in meta_data or 'region_name' not in meta_data:
                logging.error("VPC and region were not explicitly specified "
                              "and can't be auto-discovered.")
                sys.exit(1)
            else:
                conf.update(meta_data)

        try:
            logging.info("*** Starting vpc-router in %s mode ***" %
                         conf['mode'])
            watcher.start_watcher(conf)
            logging.info("*** Stopping vpc-router ***")
        except Exception as e:
            import traceback
            traceback.print_exc()
            logging.error(e.message)
            logging.error("*** Exiting")
    except Exception as e:
        print "\n*** Error: %s\n" % e.message

    sys.exit(1)