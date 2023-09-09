# -*- coding: utf-8 -*-
"""
Unit tests from mathics.builtin.datetime.
"""

import sys
import time
from test.helper import check_evaluation, evaluate

import pytest


@pytest.mark.skipif(
    sys.platform in ("win32",) or hasattr(sys, "pyston_version_info"),
    reason="TimeConstrained needs to be rewritten",
)
def test_timeremaining():
    str_expr = "TimeConstrained[1+2; TimeRemaining[], 0.9]"
    result = evaluate(str_expr)
    assert result is None or 0 < result.to_python() < 9


@pytest.mark.skip(reason="TimeConstrained needs to be rewritten")
def test_timeconstrained1():
    #
    str_expr1 = "a=1.; TimeConstrained[Do[Pause[.1];a=a+1,{1000}],1]"
    result = evaluate(str_expr1)
    str_expected = "$Aborted"
    expected = evaluate(str_expected)
    assert result == expected
    time.sleep(1)
    assert evaluate("a").to_python() == 10


def test_datelist():
    for str_expr, str_expected in (
        ('DateList["2016-09-09"]', "{2016, 9, 9, 0, 0, 0.}"),
        # strptime should ignore leading 0s
        (
            'DateList[{"6/6/91", {"Day", "Month", "YearShort"}}]',
            "{1991, 6, 6, 0, 0, 0.}",
        ),
        (
            'DateList[{"6/06/91", {"Day", "Month", "YearShort"}}]',
            "{1991, 6, 6, 0, 0, 0.}",
        ),
        (
            'DateList[{"06/06/91", {"Day", "Month", "YearShort"}}]',
            "{1991, 6, 6, 0, 0, 0.}",
        ),
        (
            'DateList[{"06/6/91", {"Day", "Month", "YearShort"}}]',
            "{1991, 6, 6, 0, 0, 0.}",
        ),
        ('DateList[{"5/18", {"Month", "Day"}}][[1]] == DateList[][[1]]', "True"),
        ("Quiet[DateList[abc]]", "DateList[abc]"),
    ):
        check_evaluation(str_expr, str_expected)


def test_datestring():
    for str_expr, str_expected in (
        ## Check Leading 0s
        # (
        #  'DateString[{1979, 3, 14}, {"DayName", "  ", "MonthShort", "-", "YearShort"}',
        # "Wednesday  3-79"
        # ),
        (
            "DateString[{1979, 3, 4}]",
            "Sun 4 Mar 1979 00:00:00",
        ),
        ('DateString[{"5/19"}]', "5/19"),
        ('DateString["2000-12-1", "Year"]', "2000"),
    ):
        check_evaluation(str_expr, str_expected, hold_expected=True)


@pytest.mark.parametrize(
    ("str_expr", "msgs", "str_expected", "fail_msg"),
    [
        ("AbsoluteTime[1000]", None, "1000", "Mathematica Bug - Mathics gets it right"),
        (
            'DateList["7/8/9"]',
            ("The interpretation of 7/8/9 is ambiguous.",),
            "{2009, 7, 8, 0, 0, 0.}",
            None,
        ),
        (
            'DateString[{1979, 3, 14}, {"DayName", "  ", "MonthShort", "-", "YearShort"}]',
            None,
            "Wednesday  3-79",
            "Check Leading 0",
        ),
        (
            'DateString[{"DayName", "  ", "Month", "/", "YearShort"}]==DateString[Now[[1]], {"DayName", "  ", "Month", "/", "YearShort"}]',
            None,
            "True",
            None,
        ),
        (
            'DateString[{"06/06/1991", {"Month", "Day", "Year"}}]',
            None,
            "Thu 6 Jun 1991 00:00:00",
            "Assumed separators",
        ),
        (
            'DateString[{"06/06/1991", {"Month", "/", "Day", "/", "Year"}}]',
            None,
            "Thu 6 Jun 1991 00:00:00",
            "Specified separators",
        ),
    ],
)
def test_private_doctests_datetime(str_expr, msgs, str_expected, fail_msg):
    """ """
    check_evaluation(
        str_expr,
        str_expected,
        to_string_expr=True,
        to_string_expected=True,
        hold_expected=True,
        failure_message=fail_msg,
        expected_messages=msgs,
    )
