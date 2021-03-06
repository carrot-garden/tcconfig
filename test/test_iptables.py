# encoding: utf-8

"""
.. codeauthor:: Tsuyoshi Hombashi <gogogo.vm@gmail.com>
"""

import random

import pytest
from subprocrunner import SubprocessRunner

from tcconfig._iptables import VALID_CHAIN_LIST
from tcconfig._iptables import IptablesMangleMark
from tcconfig._iptables import IptablesMangleController


_DEF_SRC = "192.168.0.0/24"
_DEF_DST = "192.168.100.0/24"


prerouting_mangle_mark_list = [
    IptablesMangleMark(
        line_number=1,
        mark_id=1,
        source=_DEF_SRC,
        destination=_DEF_DST,
        chain="PREROUTING",
        protocol="all"
    ),
]

input_mangle_mark_list = [
    IptablesMangleMark(
        line_number=1,
        mark_id=1234,
        source="anywhere",
        destination=_DEF_DST,
        chain="INPUT",
        protocol="all"
    ),
]

output_mangle_mark_list = [
    IptablesMangleMark(
        line_number=1,
        mark_id=12,
        source=_DEF_SRC,
        destination=_DEF_DST,
        chain="OUTPUT",
        protocol="tcp"
    ),
    IptablesMangleMark(
        line_number=2,
        mark_id=123,
        source=_DEF_SRC,
        destination="anywhere",
        chain="OUTPUT",
        protocol="all"
    ),
    IptablesMangleMark(
        line_number=3,
        mark_id=12345,
        source="anywhere",
        destination="anywhere",
        chain="OUTPUT",
        protocol="all"
    ),
]

mangle_mark_list = (
    prerouting_mangle_mark_list +
    input_mangle_mark_list +
    output_mangle_mark_list
)

reverse_mangle_mark_list = (
    list(reversed(prerouting_mangle_mark_list)) +
    list(reversed(input_mangle_mark_list)) +
    list(reversed(output_mangle_mark_list))
)


class Test_IptablesMangleMark_repr(object):

    def test_smoke(self):
        for mangle_mark in mangle_mark_list:
            assert len(str(mangle_mark)) > 0


class Test_IptablesMangleMark_to_append_command(object):
    _CMD_PREFIX = "iptables -A {:s} -t mangle -j MARK"

    @pytest.mark.parametrize(
        [
            "mark_id", "source", "destination", "chain", "protocol",
            "line_number", "expected"
        ],
        [
            [
                2, _DEF_SRC, _DEF_DST, "PREROUTING", "all", None,
                "{} --set-mark 2 -p all -s {} -d {}".format(
                    _CMD_PREFIX.format("PREROUTING"), _DEF_SRC, _DEF_DST),
            ],
            [
                2, _DEF_SRC, _DEF_DST, "OUTPUT", "all", 1,
                "{} --set-mark 2 -p all -s {} -d {}".format(
                    _CMD_PREFIX.format("OUTPUT"), _DEF_SRC, _DEF_DST),
            ],
            [
                2, _DEF_SRC, _DEF_DST, "OUTPUT", "tcp", 1,
                "{} --set-mark 2 -p tcp -s {} -d {}".format(
                    _CMD_PREFIX.format("OUTPUT"), _DEF_SRC, _DEF_DST),
            ],
            [
                100, _DEF_SRC, "anywhere", "INPUT", "all", 100,
                "{} --set-mark 100 -p all -s {}".format(
                    _CMD_PREFIX.format("INPUT"), _DEF_SRC),
            ],
            [
                1, "anywhere", _DEF_DST, "OUTPUT", "all", 100,
                "{} --set-mark 1 -p all -d {}".format(
                    _CMD_PREFIX.format("OUTPUT"), _DEF_DST),
            ],
            [
                1, "anywhere", "anywhere", "OUTPUT", "all", 100,
                "{} --set-mark 1 -p all".format(
                    _CMD_PREFIX.format("OUTPUT")),
            ],
        ]
    )
    def test_normal(
            self, mark_id, source, destination, chain, protocol, line_number,
            expected):
        mark = IptablesMangleMark(
            mark_id=mark_id, source=source, destination=destination,
            chain=chain, protocol=protocol, line_number=line_number)
        assert mark.to_append_command() == expected


class Test_IptablesMangleMark_to_delete_command(object):

    @pytest.mark.parametrize(
        [
            "mark_id", "source", "destination",  "chain", "protocol",
            "line_number", "expected"
        ],
        [
            [
                2, _DEF_SRC, _DEF_DST, "PREROUTING", "all", 1,
                "iptables -t mangle -D PREROUTING 1",
            ],
            [
                20, None, None, "OUTPUT", "all", 2,
                "iptables -t mangle -D OUTPUT 2",
            ],
        ]
    )
    def test_normal(
            self, mark_id, source, destination, chain, protocol, line_number,
            expected):
        mark = IptablesMangleMark(
            mark_id=mark_id, source=_DEF_SRC, destination=_DEF_DST,
            chain=chain, protocol=protocol, line_number=line_number)
        assert mark.to_delete_command() == expected

    @pytest.mark.parametrize(
        [
            "mark_id", "source", "destination", "chain", "protocol", "line_number",
            "expected"
        ],
        [
            [
                2, _DEF_SRC, _DEF_DST, "OUTPUT", "all", None,
                TypeError,
            ],
        ]
    )
    def test_exception(
            self, mark_id, source, destination, chain, protocol, line_number,
            expected):
        mark = IptablesMangleMark(
            mark_id=mark_id, source=source, destination=destination,
            chain=chain, protocol=protocol, line_number=line_number)
        with pytest.raises(expected):
            mark.to_delete_command()


class Test_IptablesMangleController_get_unique_mark_id(object):

    @classmethod
    def setup_class(cls):
        IptablesMangleController.clear()

    @classmethod
    def teardown_class(cls):
        IptablesMangleController.clear()

    @pytest.mark.xfail
    def test_normal(self):
        for i in range(5):
            mark_id = IptablesMangleController.get_unique_mark_id()

            assert mark_id == (i + 1)
            mangle_mark = IptablesMangleMark(
                mark_id=mark_id, source=_DEF_SRC, destination=_DEF_DST,
                chain=random.choice(VALID_CHAIN_LIST))
            assert IptablesMangleController.add(mangle_mark) == 0


class Test_IptablesMangleController_add(object):

    @classmethod
    def setup_class(cls):
        IptablesMangleController.clear()

    @classmethod
    def teardown_class(cls):
        IptablesMangleController.clear()

    @pytest.mark.xfail
    def test_normal(self):
        initial_len = len(IptablesMangleController.get_iptables())

        for mangle_mark in mangle_mark_list:
            assert IptablesMangleController.add(mangle_mark) == 0

        assert len(IptablesMangleController.get_iptables()) > initial_len


class Test_IptablesMangleController_clear(object):

    @classmethod
    def setup_class(cls):
        IptablesMangleController.clear()

    @classmethod
    def teardown_class(cls):
        IptablesMangleController.clear()

    @pytest.mark.xfail
    def test_normal(self):
        initial_len = len(IptablesMangleController.get_iptables())

        for mangle_mark in mangle_mark_list:
            assert IptablesMangleController.add(mangle_mark) == 0

        assert len(IptablesMangleController.get_iptables()) > initial_len

        IptablesMangleController.clear()

        assert len(IptablesMangleController.get_iptables()) == initial_len


class Test_IptablesMangleController_parse(object):

    @classmethod
    def setup_class(cls):
        IptablesMangleController.clear()

    @classmethod
    def teardown_class(cls):
        IptablesMangleController.clear()

    @pytest.mark.xfail
    def test_normal(self):
        for mangle_mark in mangle_mark_list:
            assert IptablesMangleController.add(mangle_mark) == 0

        for lhs_mangle, rhs_mangle in zip(
                IptablesMangleController.parse(), reverse_mangle_mark_list):

            print("lhs: {:s}".format(lhs_mangle))
            print("rhs: {:s}".format(rhs_mangle))

            assert lhs_mangle == rhs_mangle
