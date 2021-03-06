#!/usr/bin/env python
# encoding: utf-8

"""
.. codeauthor:: Tsuyoshi Hombashi <gogogo.vm@gmail.com>
"""

from __future__ import absolute_import
import sys

import dataproperty
import logbook
import pyparsing as pp
import six
import subprocrunner

import tcconfig
from .traffic_control import TrafficControl
from ._argparse_wrapper import ArgparseWrapper
from ._common import ANYWHERE_NETWORK
from ._error import ModuleNotFoundError
from ._error import NetworkInterfaceNotFoundError
from ._traffic_direction import TrafficDirection


handler = logbook.StderrHandler()
handler.push_application()


def parse_option():
    parser = ArgparseWrapper(tcconfig.VERSION)

    group = parser.parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--device",
        help="network device name (e.g. eth0)")
    group.add_argument(
        "-f", "--config-file",
        help="""setting traffic controls from a configuration file.
        output file of the tcshow.""")

    group = parser.parser.add_argument_group("Network Interface")
    group.add_argument(
        "--overwrite", action="store_true", default=False,
        help="overwrite existing settings")

    group = parser.parser.add_argument_group("Traffic Control")
    group.add_argument(
        "--direction", choices=TrafficDirection.LIST,
        default=TrafficDirection.OUTGOING,
        help="""the direction of network communication that impose traffic control.
        ``incoming`` requires linux kernel version 2.6.20 or later.
        (default = ``%(default)s``)
        """)
    group.add_argument(
        "--rate", dest="bandwidth_rate",
        help="network bandwidth rate [K|M|G bps]")
    group.add_argument(
        "--delay", dest="network_latency", type=float, default=0,
        help="round trip network delay [ms] (default=%(default)s)")
    group.add_argument(
        "--delay-distro", dest="latency_distro_ms", type=float, default=0,
        help="""
        distribution of network latency becomes X +- Y [ms]
        (normal distribution), with this option.
        (X: value of --delay option, Y: value of --delay-dist option)
        network latency distribution will be uniform without this option.
        """)
    group.add_argument(
        "--loss", dest="packet_loss_rate", type=float, default=0,
        help="round trip packet loss rate [%%] (default=%(default)s)")
    group.add_argument(
        "--corrupt", dest="corruption_rate", type=float, default=0,
        help="""
        packet corruption rate [%%]. packet corruption means single bit error
        at a random offset in the packet. (default=%(default)s)
        """)
    group.add_argument(
        "--network",
        help="Target IP address/network of traffic control")
    group.add_argument(
        "--port", type=int,
        help="port number of traffic control")

    group = parser.parser.add_argument_group("Prototype")
    group.add_argument(
        "--iptables", dest="is_enable_iptables",
        action="store_true", default=False,
        help="[experimental] use iptables to filter network")
    group.add_argument(
        "--src-network",
        help="[require iptables]")

    return parser.parser.parse_args()


def verify_netem_module():
    runner = subprocrunner.SubprocessRunner("lsmod | grep sch_netem")

    if runner.run() != 0:
        raise ModuleNotFoundError("sch_netem module not found")


class TcConfigLoader(object):

    def __init__(self, logger):
        self.__logger = logger
        self.__config_table = None
        self.is_overwrite = False

    def load_tcconfig(self, config_file_path):
        import json
        from voluptuous import Schema, Required, Any, ALLOW_EXTRA

        schema = Schema({
            Required(six.text_type): {
                Any(*TrafficDirection.LIST): {
                    six.text_type: {
                        six.text_type: six.text_type,
                    },
                }
            },
        }, extra=ALLOW_EXTRA)

        with open(config_file_path) as fp:
            self.__config_table = json.load(fp)

        schema(self.__config_table)
        self.__logger.debug("tc config file: {:s}".format(
            json.dumps(self.__config_table, indent=4)))

    def get_tcconfig_command_list(self):
        command_list = []

        for device, device_table in six.iteritems(self.__config_table):
            if self.is_overwrite:
                command_list.append("tcdel --device " + device)

            for direction, direction_table in six.iteritems(device_table):
                for tc_filter, filter_table in six.iteritems(direction_table):
                    if filter_table == {}:
                        continue

                    option_list = [
                        "--device=" + device,
                        "--direction=" + direction,
                    ] + [
                        "--{:s}={:s}".format(k, v)
                        for k, v in six.iteritems(filter_table)
                    ]

                    try:
                        network = self.__parse_tc_filter_network(tc_filter)
                        if network != ANYWHERE_NETWORK:
                            option_list.append("--network=" + network)
                    except pp.ParseException:
                        pass

                    try:
                        port = self.__parse_tc_filter_port(tc_filter)
                        option_list.append("--port=" + port)
                    except pp.ParseException:
                        pass

                    command_list.append(" ".join(["tcset"] + option_list))

        return command_list

    @staticmethod
    def __parse_tc_filter_network(text):
        network_pattern = (
            pp.SkipTo("network=", include=True) +
            pp.Word(pp.alphanums + "." + "/"))

        return network_pattern.parseString(text)[-1]

    @staticmethod
    def __parse_tc_filter_port(text):
        port_pattern = (
            pp.SkipTo("port=", include=True) +
            pp.Word(pp.nums))

        return port_pattern.parseString(text)[-1]


def set_tc_from_file(logger, config_file_path, is_overwrite):
    return_code = 0

    loader = TcConfigLoader(logger)
    loader.is_overwrite = is_overwrite
    loader.load_tcconfig(config_file_path)

    for tcconfig_command in loader.get_tcconfig_command_list():
        return_code |= subprocrunner.SubprocessRunner(
            tcconfig_command).run()

    return return_code


def main():
    options = parse_option()
    logger = logbook.Logger("tcset")
    logger.level = options.log_level

    subprocrunner.logger.level = options.log_level
    if options.quiet:
        subprocrunner.logger.disable()
    else:
        subprocrunner.logger.enable()

    subprocrunner.Which("tc").verify()
    try:
        verify_netem_module()
    except ModuleNotFoundError as e:
        logger.debug(str(e))
    except subprocrunner.CommandNotFoundError as e:
        logger.error(str(e))

    if dataproperty.is_not_empty_string(options.config_file):
        return set_tc_from_file(logger, options.config_file, options.overwrite)

    tc = TrafficControl(
        options.device,
        direction=options.direction,
        bandwidth_rate=options.bandwidth_rate,
        latency_ms=options.network_latency,
        latency_distro_ms=options.latency_distro_ms,
        packet_loss_rate=options.packet_loss_rate,
        corruption_rate=options.corruption_rate,
        network=options.network,
        src_network=options.src_network,
        port=options.port,
        is_enable_iptables=options.is_enable_iptables
    )

    try:
        tc.validate()
    except (NetworkInterfaceNotFoundError, ValueError) as e:
        logger.error(str(e))
        return 1

    if options.overwrite:
        try:
            tc.delete_tc()
        except NetworkInterfaceNotFoundError:
            pass

    tc.set_tc()

    return 0


if __name__ == '__main__':
    sys.exit(main())
