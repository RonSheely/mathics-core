# -*- coding: utf-8 -*-
"""
Rules and Patterns

The concept of transformation rules for arbitrary symbolic patterns is key \
in \\Mathics.

Also, functions can get applied or transformed depending on whether or not \
functions arguments match.

Some examples:
    >> a + b + c /. a + b -> t
     = c + t
    >> a + 2 + b + c + x * y /. n_Integer + s__Symbol + rest_ -> {n, s, rest}
     = {2, a, b + c + x y}
    >> f[a, b, c, d] /. f[first_, rest___] -> {first, {rest}}
     = {a, {b, c, d}}

Tests and Conditions:
    >> f[4] /. f[x_?(# > 0&)] -> x ^ 2
     = 16
    >> f[4] /. f[x_] /; x > 0 -> x ^ 2
     = 16

Elements in the beginning of a pattern rather match fewer elements:
    >> f[a, b, c, d] /. f[start__, end__] -> {{start}, {end}}
     = {{a}, {b, c, d}}

Optional arguments using 'Optional':
    >> f[a] /. f[x_, y_:3] -> {x, y}
     = {a, 3}

Options using 'OptionsPattern' and 'OptionValue':
    >> f[y, a->3] /. f[x_, OptionsPattern[{a->2, b->5}]] -> {x, OptionValue[a], OptionValue[b]}
     = {y, 3, 5}

The attributes 'Flat', 'Orderless', and 'OneIdentity' affect pattern matching.
"""

from typing import List, Optional as OptionalType, Tuple, Union

from mathics.core.atoms import Integer, Integer2, Number, Rational, Real, String
from mathics.core.attributes import (
    A_HOLD_ALL,
    A_HOLD_FIRST,
    A_HOLD_REST,
    A_PROTECTED,
    A_SEQUENCE_HOLD,
)
from mathics.core.builtin import (
    AtomBuiltin,
    BinaryOperator,
    Builtin,
    PatternError,
    PatternObject,
    PostfixOperator,
    Test,
)
from mathics.core.element import BaseElement, EvalMixin
from mathics.core.evaluation import Evaluation
from mathics.core.exceptions import InvalidLevelspecError
from mathics.core.expression import Expression, SymbolVerbatim
from mathics.core.list import ListExpression
from mathics.core.pattern import BasePattern, StopGenerator
from mathics.core.rules import Rule
from mathics.core.symbols import Atom, Symbol, SymbolList, SymbolTrue
from mathics.core.systemsymbols import (
    SymbolBlank,
    SymbolDefault,
    SymbolDispatch,
    SymbolInfinity,
    SymbolRule,
    SymbolRuleDelayed,
)
from mathics.eval.parts import python_levelspec

# This tells documentation how to sort this module
sort_order = "mathics.builtin.rules-and-patterns"


class Rule_(BinaryOperator):
    """

    <url>:WMA link:https://reference.wolfram.com/language/ref/Rule_.html</url>

    <dl>
      <dt>'Rule[$x$, $y$]'
      <dt>'$x$ -> $y$'
      <dd>represents a rule replacing $x$ with $y$.
    </dl>

    >> a+b+c /. c->d
    = a + b + d
    >> {x,x^2,y} /. x->3
     = {3, 9, y}
    >> a /. Rule[1, 2, 3] -> t
     : Rule called with 3 arguments; 2 arguments are expected.
     = a
    """

    name = "Rule"
    operator = "->"
    attributes = A_SEQUENCE_HOLD | A_PROTECTED
    grouping = "Right"
    needs_verbatim = True
    summary_text = "a replacement rule"

    def eval_rule(self, elems, evaluation):
        """Rule[elems___]"""
        num_parms = len(elems.get_sequence())
        if num_parms != 2:
            evaluation.message("Rule", "argrx", "Rule", Integer(num_parms), Integer2)
        return None


class RuleDelayed(BinaryOperator):
    """
    <url>:WMA link:https://reference.wolfram.com/language/ref/RuleDelayed.html</url>

    <dl>
      <dt>'RuleDelayed[$x$, $y$]'
      <dt>'$x$ :> $y$'
      <dd>represents a rule replacing $x$ with $y$, with $y$ held
        unevaluated.
    </dl>

    >> Attributes[RuleDelayed]
     = {HoldRest, Protected, SequenceHold}
    """

    attributes = A_SEQUENCE_HOLD | A_HOLD_REST | A_PROTECTED
    needs_verbatim = True
    operator = ":>"
    summary_text = "a rule that keeps the replacement unevaluated"

    def eval_rule_delayed(self, elems, evaluation):
        """RuleDelayed[elems___]"""
        num_parms = len(elems.get_sequence())
        if num_parms != 2:
            evaluation.message(
                "RuleDelayed", "argrx", "RuleDelayed", Integer(num_parms), Integer2
            )
        return None


# TODO: disentangle me
def create_rules(
    rules_expr: BaseElement,
    expr: Expression,
    name: str,
    evaluation: Evaluation,
    extra_args: OptionalType[List] = None,
) -> Tuple[Union[List[Rule], BaseElement], bool]:
    """
    This function implements  `Replace`, `ReplaceAll`, `ReplaceRepeated`
    and `ReplaceList` eval methods.
    `name` controls which of these methods is implemented. These methods
    applies the rule / list of rules
    `rules_expr` over the expression `expr`, using the evaluation context
    `evaluation`.

    The result is a tuple of two elements. If the second element is `True`,
    then the first element is the result of the method.
    If `False`, the first element of the tuple is a list of rules.

    """
    if isinstance(rules_expr, Dispatch):
        return rules_expr.rules, False
    if rules_expr.has_form("Dispatch", None):
        return Dispatch(rules_expr.elements, evaluation)

    if rules_expr.has_form("List", None):
        rules = rules_expr.elements
    else:
        rules = [rules_expr]
    any_lists = False
    for item in rules:
        if item.get_head() in (SymbolList, SymbolDispatch):
            any_lists = True
            break

    if any_lists:
        all_lists = True
        for item in rules:
            if item.get_head() is not SymbolList:
                all_lists = False
                break

        if all_lists:
            if extra_args is None:
                extra_args = []
            return (
                ListExpression(
                    *[
                        Expression(Symbol(name), expr, item, *extra_args)
                        for item in rules
                    ]
                ),
                True,
            )

        evaluation.message(name, "rmix", rules_expr)
        return None, True

    result = []
    for rule in rules:
        if rule.head not in (SymbolRule, SymbolRuleDelayed):
            evaluation.message(name, "reps", rule)
            return None, True
        if len(rule.elements) != 2:
            evaluation.message(
                # TODO: shorten names here
                rule.get_head_name(),
                "argrx",
                rule.get_head_name(),
                3,
                2,
            )
            return None, True

        result.append(Rule(rule.elements[0], rule.elements[1]))
    return result, False


class Replace(Builtin):
    """

    <url>
    :WMA link:
    https://reference.wolfram.com/language/ref/Replace.html</url>

    <dl>
      <dt>'Replace[$expr$, $x$ -> $y$]'
      <dd>yields the result of replacing $expr$ with $y$ if it
        matches the pattern $x$.
      <dt>'Replace[$expr$, $x$ -> $y$, $levelspec$]'
      <dd>replaces only subexpressions at levels specified through
        $levelspec$.
      <dt>'Replace[$expr$, {$x$ -> $y$, ...}]'
      <dd>performs replacement with multiple rules, yielding a
        single result expression.
      <dt>'Replace[$expr$, {{$a$ -> $b$, ...}, {$c$ -> $d$, ...}, ...}]'
      <dd>returns a list containing the result of performing each
        set of replacements.
    </dl>

    >> Replace[x, {x -> 2}]
     = 2

    By default, only the top level is searched for matches
    >> Replace[1 + x, {x -> 2}]
     = 1 + x

    >> Replace[x, {{x -> 1}, {x -> 2}}]
     = {1, 2}

    Replace stops after the first replacement
    >> Replace[x, {x -> {}, _List -> y}]
     = {}

    Replace replaces the deepest levels first
    >> Replace[x[1], {x[1] -> y, 1 -> 2}, All]
     = x[2]

    By default, heads are not replaced
    >> Replace[x[x[y]], x -> z, All]
     = x[x[y]]

    Heads can be replaced using the Heads option
    >> Replace[x[x[y]], x -> z, All, Heads -> True]
     = z[z[y]]

    Note that heads are handled at the level of elements
    >> Replace[x[x[y]], x -> z, {1}, Heads -> True]
     = z[x[y]]

    You can use Replace as an operator
    >> Replace[{x_ -> x + 1}][10]
     = 11
    """

    messages = {
        "reps": "`1` is not a valid replacement rule.",
        "rmix": "Elements of `1` are a mixture of lists and nonlists.",
    }

    options = {"Heads": "False"}
    rules = {"Replace[rules_][expr_]": "Replace[expr, rules]"}
    summary_text = "apply a replacement rule"

    def eval_levelspec(self, expr, rules, ls, evaluation, options):
        "Replace[expr_, rules_, Optional[Pattern[ls, _?LevelQ], {0}], OptionsPattern[Replace]]"
        try:
            rules, ret = create_rules(rules, expr, "Replace", evaluation)
            if ret:
                return rules

            heads = self.get_option(options, "Heads", evaluation) is SymbolTrue

            result, _ = expr.do_apply_rules(
                rules,
                evaluation,
                level=0,
                options={"levelspec": python_levelspec(ls), "heads": heads},
            )
            return result
        except InvalidLevelspecError:
            evaluation.message("General", "level", ls)

        except PatternError:
            evaluation.message("Replace", "reps", rules)

        return None


class ReplaceAll(BinaryOperator):
    """
    <url>
    :WMA link:
    https://reference.wolfram.com/language/ref/ReplaceAll.html</url>

    <dl>
      <dt>'ReplaceAll[$expr$, $x$ -> $y$]'
      <dt>'$expr$ /. $x$ -> $y$'
      <dd>yields the result of replacing all subexpressions of
        $expr$ matching the pattern $x$ with $y$.
      <dt>'$expr$ /. {$x$ -> $y$, ...}'
      <dd>performs replacement with multiple rules, yielding a
        single result expression.
      <dt>'$expr$ /. {{$a$ -> $b$, ...}, {$c$ -> $d$, ...}, ...}'
      <dd>returns a list containing the result of performing each
        set of replacements.
    </dl>

    >> a+b+c /. c->d
     = a + b + d
    >> g[a+b+c,a]/.g[x_+y_,x_]->{x,y}
     = {a, b + c}

    If $rules$ is a list of lists, a list of all possible respective
    replacements is returned:
    >> {a, b} /. {{a->x, b->y}, {a->u, b->v}}
     = {{x, y}, {u, v}}
    The list can be arbitrarily nested:
    >> {a, b} /. {{{a->x, b->y}, {a->w, b->z}}, {a->u, b->v}}
     = {{{x, y}, {w, z}}, {u, v}}
    >> {a, b} /. {{{a->x, b->y}, a->w, b->z}, {a->u, b->v}}
     : Elements of {{a -> x, b -> y}, a -> w, b -> z} are a mixture of lists and nonlists.
     = {{a, b} /. {{a -> x, b -> y}, a -> w, b -> z}, {u, v}}

    ReplaceAll also can be used as an operator:
    >> ReplaceAll[{a -> 1}][{a, b}]
     = {1, b}

    ReplaceAll replaces the shallowest levels first:
    >> ReplaceAll[x[1], {x[1] -> y, 1 -> 2}]
     = y
    """

    grouping = "Left"
    needs_verbatim = True
    operator = "/."

    messages = {
        "reps": "`1` is not a valid replacement rule.",
        "rmix": "Elements of `1` are a mixture of lists and nonlists.",
    }

    rules = {"ReplaceAll[rules_][expr_]": "ReplaceAll[expr, rules]"}
    summary_text = "apply a replacement rule on each subexpression"

    def eval(self, expr, rules, evaluation: Evaluation):
        "ReplaceAll[expr_, rules_]"
        try:
            rules, ret = create_rules(rules, expr, "ReplaceAll", evaluation)
            if ret:
                return rules
            result, _ = expr.do_apply_rules(rules, evaluation)
            return result
        except PatternError:
            evaluation.message("Replace", "reps", rules)
            return None


class ReplaceRepeated(BinaryOperator):
    """

    <url>
    :WMA link:
    https://reference.wolfram.com/language/ref/ReplaceRepeated.html</url>

    <dl>
      <dt>'ReplaceRepeated[$expr$, $x$ -> $y$]'
      <dt>'$expr$ //. $x$ -> $y$'
      <dd>repeatedly applies the rule '$x$ -> $y$' to $expr$ until
        the result no longer changes.
    </dl>

    >> a+b+c //. c->d
     = a + b + d

    >> f = ReplaceRepeated[c->d];
    >> f[a+b+c]
     = a + b + d
    >> Clear[f];

    Simplification of logarithms:
    >> logrules = {Log[x_ * y_] :> Log[x] + Log[y], Log[x_ ^ y_] :> y * Log[x]};
    >> Log[a * (b * c) ^ d ^ e * f] //. logrules
     = Log[a] + Log[f] + (Log[b] + Log[c]) d ^ e
    'ReplaceAll' just performs a single replacement:
    >> Log[a * (b * c) ^ d ^ e * f] /. logrules
     = Log[a] + Log[f (b c) ^ d ^ e]
    """

    grouping = "Left"
    needs_verbatim = True
    operator = "//."

    messages = {
        "reps": "`1` is not a valid replacement rule.",
        "rmix": "Elements of `1` are a mixture of lists and nonlists.",
    }

    options = {
        "MaxIterations": "65535",
    }

    rules = {
        "ReplaceRepeated[rules_][expr_]": "ReplaceRepeated[expr, rules]",
    }
    summary_text = "iteratively replace until the expression does not change anymore"

    def eval_list(
        self,
        expr: BaseElement,
        rules: BaseElement,
        evaluation: Evaluation,
        options: dict,
    ) -> OptionalType[BaseElement]:
        "ReplaceRepeated[expr_, rules_, OptionsPattern[ReplaceRepeated]]"
        try:
            rules, ret = create_rules(rules, expr, "ReplaceRepeated", evaluation)
        except PatternError:
            evaluation.message("Replace", "reps", rules)
            return None

        if ret:
            return rules

        maxit = self.get_option(options, "MaxIterations", evaluation)
        if maxit.is_numeric(evaluation):
            maxit = maxit.get_int_value()
        else:
            maxit = -1

        while True:
            evaluation.check_stopped()
            if maxit == 0:
                break
            maxit -= 1
            result, applied = expr.do_apply_rules(rules, evaluation)
            if applied:
                result = result.evaluate(evaluation)
            if applied and not result.sameQ(expr):
                expr = result
            else:
                break

        return result


class ReplaceList(Builtin):
    """
    <url>
    :WMA link:
    https://reference.wolfram.com/language/ref/ReplaceList.html</url>

    <dl>
      <dt>'ReplaceList[$expr$, $rules$]'
      <dd>returns a list of all possible results when applying $rules$ \
        to $expr$.
      <dt>'ReplaceList[$expr$, $rules$, $n$]'
      <dd>returns a list of at most $n$ results when applying $rules$ \
        to $expr$.
    </dl>

    Get all subsequences of a list:
    >> ReplaceList[{a, b, c}, {___, x__, ___} -> {x}]
     = {{a}, {a, b}, {a, b, c}, {b}, {b, c}, {c}}
    You can specify the maximum number of items:
    >> ReplaceList[{a, b, c}, {___, x__, ___} -> {x}, 3]
     = {{a}, {a, b}, {a, b, c}}
    >> ReplaceList[{a, b, c}, {___, x__, ___} -> {x}, 0]
     = {}
    If no rule matches, an empty list is returned:
    >> ReplaceList[a, b->x]
     = {}

    Like in 'ReplaceAll', $rules$ can be a nested list:
    >> ReplaceList[{a, b, c}, {{{___, x__, ___} -> {x}}, {{a, b, c} -> t}}, 2]
     = {{{a}, {a, b}}, {t}}
    >> ReplaceList[expr, {}, -1]
     : Non-negative integer or Infinity expected at position 3.
     = ReplaceList[expr, {}, -1]

    Possible matches for a sum:
    >> ReplaceList[a + b + c, x_ + y_ -> {x, y}]
     = {{a, b + c}, {b, a + c}, {c, a + b}, {a + b, c}, {a + c, b}, {b + c, a}}
    """

    messages = {
        "reps": "`1` is not a valid replacement rule.",
        "rmix": "Elements of `1` are a mixture of lists and nonlists.",
    }
    summary_text = "list of possible replacement results"

    def eval(
        self,
        expr: BaseElement,
        rules: BaseElement,
        maxidx: Number,
        evaluation: Evaluation,
    ) -> OptionalType[BaseElement]:
        "ReplaceList[expr_, rules_, maxidx_:Infinity]"

        # TODO: the below handles Infinity getting added as a
        # default argument, when it is passed explitly, e.g.
        # ReplaceList[expr, {}, Infinity], then Infinity
        # comes in as DirectedInfinity[1].
        if maxidx == SymbolInfinity:
            max_count = None
        else:
            max_count = maxidx.get_int_value()
            if max_count is None or max_count < 0:
                evaluation.message("ReplaceList", "innf", 3)
                return None
        try:
            rules, ret = create_rules(
                rules, expr, "ReplaceList", evaluation, extra_args=[maxidx]
            )
        except PatternError:
            evaluation.message("Replace", "reps", rules)
            return None

        if ret:
            return rules

        list_result = []
        for rule in rules:
            result = rule.apply(expr, evaluation, return_list=True, max_list=max_count)
            list_result.extend(result)

        return ListExpression(*list_result)


class PatternTest(BinaryOperator, PatternObject):
    """

    <url>
    :WMA link:
    https://reference.wolfram.com/language/ref/PatternTest.html</url>

    <dl>
      <dt>'PatternTest[$pattern$, $test$]'
      <dt>'$pattern$ ? $test$'
      <dd>constrains $pattern$ to match $expr$ only if the
        evaluation of '$test$[$expr$]' yields 'True'.
    </dl>

    >> MatchQ[3, _Integer?(#>0&)]
     = True
    >> MatchQ[-3, _Integer?(#>0&)]
     = False
    >> MatchQ[3, Pattern[3]]
     : First element in pattern Pattern[3] is not a valid pattern name.
     = False
    """

    arg_counts = [2]
    operator = "?"
    summary_text = "match to a pattern conditioned to a test result"

    def init(
        self, expr: Expression, evaluation: OptionalType[Evaluation] = None
    ) -> None:
        super().init(expr, evaluation=evaluation)
        # This class has an important effect in the general performance,
        # since all the rules that requires specify the type of patterns
        # call it. Then, for simple checks like `NumberQ` or `NumericQ`
        # it is important to have the fastest possible implementation.
        # To to this, we overwrite the match method taking it from the
        # following dictionary. Here also would get some advantage by
        # singletonizing the Symbol class and accessing this dictionary
        # using an id() instead a string...

        match_functions = {
            "System`AtomQ": self.match_atom,
            "System`StringQ": self.match_string,
            "System`NumericQ": self.match_numericq,
            "System`NumberQ": self.match_numberq,
            "System`RealValuedNumberQ": self.match_real_numberq,
            "Internal`RealValuedNumberQ": self.match_real_numberq,
            "System`Posive": self.match_positive,
            "System`Negative": self.match_negative,
            "System`NonPositive": self.match_nonpositive,
            "System`NonNegative": self.match_nonnegative,
        }

        self.pattern = BasePattern.create(expr.elements[0], evaluation=evaluation)
        self.test = expr.elements[1]
        testname = self.test.get_name()
        self.test_name = testname
        match_function = match_functions.get(testname, None)
        if match_function:
            self.match = match_function

    def match_atom(self, expression: Expression, pattern_context: dict):
        """Match function for AtomQ"""
        yield_func = pattern_context["yield_func"]

        def yield_match(vars_2, rest):
            items = expression.get_sequence()
            # Here we use a `for` loop instead an all over iterator
            # because in Cython this is faster, since it avoids a function
            # call. For pure Python, it is the opposite.
            for item in items:
                if not isinstance(item, Atom):
                    break
            else:
                yield_func(vars_2, None)

        # TODO: clarify why we need to use copy here.
        pattern_context = pattern_context.copy()
        pattern_context["yield_func"] = yield_match
        self.pattern.match(expression, pattern_context)

    def match_string(self, expression: Expression, pattern_context: dict):
        """Match function for StringQ"""
        yield_func = pattern_context["yield_func"]

        def yield_match(vars_2, rest):
            items = expression.get_sequence()
            for item in items:
                if not isinstance(item, String):
                    break
            else:
                yield_func(vars_2, None)

        pattern_context = pattern_context.copy()
        pattern_context["yield_func"] = yield_match
        self.pattern.match(expression, pattern_context)

    def match_numberq(self, expression: Expression, pattern_context: dict):
        """Match function for NumberQ"""
        yield_func = pattern_context["yield_func"]

        def yield_match(vars_2, rest):
            items = expression.get_sequence()
            for item in items:
                if not isinstance(item, Number):
                    break
            else:
                yield_func(vars_2, None)

        pattern_context = pattern_context.copy()
        pattern_context["yield_func"] = yield_match
        self.pattern.match(expression, pattern_context)

    def match_numericq(self, expression: Expression, pattern_context: dict):
        """Match function for NumericQ"""
        yield_func = pattern_context["yield_func"]
        evaluation = pattern_context["evaluation"]

        def yield_match(vars_2, rest):
            items = expression.get_sequence()
            for item in items:
                if not (isinstance(item, Number) or item.is_numeric(evaluation)):
                    break
            else:
                yield_func(vars_2, None)

        pattern_context = pattern_context.copy()
        pattern_context["yield_func"] = yield_match
        self.pattern.match(expression, pattern_context)

    def match_real_numberq(self, expression: Expression, pattern_context: dict):
        """Match function for RealValuedNumberQ"""
        yield_func = pattern_context["yield_func"]

        def yield_match(vars_2, rest):
            items = expression.get_sequence()
            for item in items:
                if not isinstance(item, (Integer, Rational, Real)):
                    break
            else:
                yield_func(vars_2, None)

        pattern_context = pattern_context.copy()
        pattern_context["yield_func"] = yield_match
        self.pattern.match(expression, pattern_context)

    def match_positive(self, expression: Expression, pattern_context: dict):
        """Match function for PositiveQ"""
        yield_func = pattern_context["yield_func"]

        def yield_match(vars_2, rest):
            items = expression.get_sequence()
            if all(
                isinstance(item, (Integer, Rational, Real)) and item.value > 0
                for item in items
            ):
                yield_func(vars_2, None)

        pattern_context = pattern_context.copy()
        pattern_context["yield_func"] = yield_match
        self.pattern.match(expression, pattern_context)

    def match_negative(self, expression: Expression, pattern_context: dict):
        """Match function for NegativeQ"""
        yield_func = pattern_context["yield_func"]

        def yield_match(vars_2, rest):
            items = expression.get_sequence()
            if all(
                isinstance(item, (Integer, Rational, Real)) and item.value < 0
                for item in items
            ):
                yield_func(vars_2, None)

        pattern_context = pattern_context.copy()
        pattern_context["yield_func"] = yield_match
        self.pattern.match(expression, pattern_context)

    def match_nonpositive(self, expression: Expression, pattern_context: dict):
        """Match function for NonPositiveQ"""
        yield_func = pattern_context["yield_func"]

        def yield_match(vars_2, rest):
            items = expression.get_sequence()
            if all(
                isinstance(item, (Integer, Rational, Real)) and item.value <= 0
                for item in items
            ):
                yield_func(vars_2, None)

        pattern_context = pattern_context.copy()
        pattern_context["yield_func"] = yield_match
        self.pattern.match(expression, pattern_context)

    def match_nonnegative(self, expression: Expression, pattern_context: dict):
        """Match function for NonNegativeQ"""
        yield_func = pattern_context["yield_func"]

        def yield_match(vars_2, rest):
            items = expression.get_sequence()
            if all(
                isinstance(item, (Integer, Rational, Real)) and item.value >= 0
                for item in items
            ):
                yield_func(vars_2, None)

        pattern_context = pattern_context.copy()
        pattern_context["yield_func"] = yield_match
        self.pattern.match(expression, pattern_context)

    def quick_pattern_test(self, candidate, test, evaluation: Evaluation):
        """Pattern test for some other special cases"""
        if test == "System`NegativePowerQ":
            return (
                candidate.has_form("Power", 2)
                and isinstance(candidate.elements[1], (Integer, Rational, Real))
                and candidate.elements[1].value < 0
            )
        if test == "System`NotNegativePowerQ":
            return not (
                candidate.has_form("Power", 2)
                and isinstance(candidate.elements[1], (Integer, Rational, Real))
                and candidate.elements[1].value < 0
            )

        builtin = None
        builtin = evaluation.definitions.get_definition(test)
        if builtin:
            builtin = builtin.builtin
        if builtin is not None and isinstance(builtin, Test):
            return builtin.test(candidate)
        return None

    def match(self, expression: Expression, pattern_context: dict):
        """Match expression with PatternTest"""
        evaluation = pattern_context["evaluation"]
        vars_dict = pattern_context["vars_dict"]
        yield_func = pattern_context["yield_func"]

        # def match(self, yield_func, expression, vars_dict, evaluation, **kwargs):
        # for vars_2, rest in self.pattern.match(expression, vars_dict, evaluation):
        def yield_match(vars_2, rest):
            testname = self.test_name
            items = expression.get_sequence()
            for item in items:
                item = item.evaluate(evaluation)
                quick_test = self.quick_pattern_test(item, testname, evaluation)
                if quick_test is False:
                    break
                if quick_test is True:
                    continue
                    # raise StopGenerator
                test_expr = Expression(self.test, item)
                test_value = test_expr.evaluate(evaluation)
                if test_value is not SymbolTrue:
                    break
                    # raise StopGenerator
            else:
                yield_func(vars_2, None)

        # try:
        self.pattern.match(
            expression,
            {
                "yield_func": yield_match,
                "vars_dict": vars_dict,
                "evaluation": evaluation,
            },
        )
        # except StopGenerator:
        #    pass

    def get_match_count(self, vars_dict: OptionalType[dict] = None):
        return self.pattern.get_match_count(vars_dict)


class Alternatives(BinaryOperator, PatternObject):
    """
    <url>
    :WMA link:
    https://reference.wolfram.com/language/ref/Alternatives.html</url>

    <dl>
      <dt>'Alternatives[$p1$, $p2$, ..., $p_i$]'
      <dt>'$p1$ | $p2$ | ... | $p_i$'
      <dd>is a pattern that matches any of the patterns '$p1$, $p2$,
        ...., $p_i$'.
    </dl>

    >> a+b+c+d/.(a|b)->t
     = c + d + 2 t

    Alternatives can also be used for string expressions
    >> StringReplace["0123 3210", "1" | "2" -> "X"]
     = 0XX3 3XX0
    """

    arg_counts = None
    needs_verbatim = True
    operator = "|"
    summary_text = "match to any of several patterns"

    def init(
        self, expr: Expression, evaluation: OptionalType[Evaluation] = None
    ) -> None:
        super().init(expr, evaluation=evaluation)
        self.alternatives = [
            BasePattern.create(element, evaluation=evaluation)
            for element in expr.elements
        ]

    def match(self, expression: Expression, pattern_context: dict):
        """Match with Alternatives"""
        for alternative in self.alternatives:
            # for new_vars_dict, rest in alternative.match(
            #     expression, vars_dict, evaluation):
            #     yield_func(new_vars_dict, rest)
            alternative.match(expression, pattern_context)

    def get_match_count(
        self, vars_dict: OptionalType[dict] = None
    ) -> Union[None, int, tuple]:
        range_lst = None
        for alternative in self.alternatives:
            sub = alternative.get_match_count(vars_dict)
            if range_lst is None:
                range_lst = tuple(sub)
            else:
                if sub[0] < range_lst[0]:
                    range_lst[0] = sub[0]
                if range_lst[1] is None or sub[1] > range_lst[1]:
                    range_lst[1] = sub[1]
        return tuple(range_lst)


class _StopGeneratorExcept(StopGenerator):
    pass


class Except(PatternObject):
    """
    <url>
    :WMA link:
    https://reference.wolfram.com/language/ref/Except.html</url>

    <dl>
      <dt>'Except[$c$]'
      <dd>represents a pattern object that matches any expression except \
          those matching $c$.

      <dt>'Except[$c$, $p$]'
      <dd>represents a pattern object that matches $p$ but not $c$.
    </dl>

    >> Cases[{x, a, b, x, c}, Except[x]]
     = {a, b, c}

    >> Cases[{a, 0, b, 1, c, 2, 3}, Except[1, _Integer]]
     = {0, 2, 3}

    Except can also be used for string expressions:
    >> StringReplace["Hello world!", Except[LetterCharacter] -> ""]
     = Helloworld
    """

    arg_counts = [1, 2]
    summary_text = "match to expressions that do not match with a pattern"

    def init(
        self, expr: Expression, evaluation: OptionalType[Evaluation] = None
    ) -> None:
        super().init(expr, evaluation=evaluation)
        self.c = BasePattern.create(expr.elements[0], evaluation=evaluation)
        if len(expr.elements) == 2:
            self.p = BasePattern.create(expr.elements[1], evaluation=evaluation)
        else:
            self.p = BasePattern.create(Expression(SymbolBlank), evaluation=evaluation)

    def match(self, expression: Expression, pattern_context: dict):
        """Match with Exception Pattern"""

        def except_yield_func(vars_dict, rest):
            raise _StopGeneratorExcept(True)

        new_pattern_context = pattern_context.copy()
        new_pattern_context["yield_func"] = except_yield_func

        try:
            self.c.match(expression, new_pattern_context)
        except _StopGeneratorExcept:
            pass
        else:
            self.p.match(expression, pattern_context)


class Verbatim(PatternObject):
    """
    <url>
    :WMA link:
    https://reference.wolfram.com/language/ref/Verbatim.html</url>

    <dl>
      <dt>'Verbatim[$expr$]'
      <dd>prevents pattern constructs in $expr$ from taking effect,
        allowing them to match themselves.
    </dl>

    Create a pattern matching 'Blank':
    >> _ /. Verbatim[_]->t
     = t
    >> x /. Verbatim[_]->t
     = x

    Without 'Verbatim', 'Blank' has its normal effect:
    >> x /. _->t
     = t
    """

    arg_counts = [1, 2]
    summary_text = "take the pattern elements as literals"

    def init(
        self, expr: Expression, evaluation: OptionalType[Evaluation] = None
    ) -> None:
        super().init(expr, evaluation=evaluation)
        self.content = expr.elements[0]

    def match(self, expression: Expression, pattern_context: dict):
        """Match with Verbatim Pattern"""
        vars_dict = pattern_context["vars_dict"]
        yield_func = pattern_context["yield_func"]

        if self.content.sameQ(expression):
            yield_func(vars_dict, None)


class HoldPattern(PatternObject):
    """

    <url>:WMA link:https://reference.wolfram.com/language/ref/HoldPattern.html</url>

    <dl>
      <dt>'HoldPattern[$expr$]'
      <dd>is equivalent to $expr$ for pattern matching, but
        maintains it in an unevaluated form.
    </dl>

    >> HoldPattern[x + x]
     = HoldPattern[x + x]
    >> x /. HoldPattern[x] -> t
     = t

    'HoldPattern' has attribute 'HoldAll':
    >> Attributes[HoldPattern]
     = {HoldAll, Protected}
    """

    arg_counts = [1]
    attributes = A_HOLD_ALL | A_PROTECTED
    summary_text = "took the expression as a literal pattern"

    def init(
        self, expr: Expression, evaluation: OptionalType[Evaluation] = None
    ) -> None:
        super().init(expr, evaluation=evaluation)
        self.pattern = BasePattern.create(expr.elements[0], evaluation=evaluation)

    def match(self, expression: Expression, pattern_context: dict):
        # for new_vars_dict, rest in self.pattern.match(
        #     expression, vars_dict, evaluation):
        #     yield new_vars_dict, rest
        self.pattern.match(expression, pattern_context)


class Pattern(PatternObject):
    """
    <url>:WMA link:https://reference.wolfram.com/language/ref/Pattern.html</url>

    <dl>
      <dt>'Pattern[$symb$, $patt$]'
      <dt>'$symb$ : $patt$'
      <dd>assigns the name $symb$ to the pattern $patt$.
      <dt>'$symb$_$head$'
      <dd>is equivalent to '$symb$ : _$head$' (accordingly with '__'
        and '___').
      <dt>'$symb$ : $patt$ : $default$'
      <dd>is a pattern with name $symb$ and default value $default$,
        equivalent to 'Optional[$patt$ : $symb$, $default$]'.
    </dl>

    >> FullForm[a_b]
     = Pattern[a, Blank[b]]
    >> FullForm[a:_:b]
     = Optional[Pattern[a, Blank[]], b]

    'Pattern' has attribute 'HoldFirst', so it does not evaluate its name:
    >> x = 2
     = 2
    >> x_
     = x_

    Nested 'Pattern' assign multiple names to the same pattern. Still,
    the last parameter is the default value.
    >> f[y] /. f[a:b,_:d] -> {a, b}
     = f[y]
    This is equivalent to:
    >> f[a] /. f[a:_:b] -> {a, b}
     = {a, b}
    'FullForm':
    >> FullForm[a:b:c:d:e]
     = Optional[Pattern[a, b], Optional[Pattern[c, d], e]]

    >> f[] /. f[a:_:b] -> {a, b}
     = {b, b}
    """

    name = "Pattern"

    arg_counts = [2]

    attributes = A_HOLD_FIRST | A_PROTECTED

    messages = {
        "patvar": "First element in pattern `1` is not a valid pattern name.",
        "nodef": (
            "No default setting found for `1` in " "position `2` when length is `3`."
        ),
    }

    rules = {
        (
            "MakeBoxes[Verbatim[Pattern][symbol_Symbol, blank_Blank|"
            "blank_BlankSequence|blank_BlankNullSequence], "
            "f:StandardForm|TraditionalForm|InputForm|OutputForm]"
        ): "MakeBoxes[symbol, f] <> MakeBoxes[blank, f]",
        # 'StringForm["`1``2`", HoldForm[symbol], blank]',
    }

    formats = {
        "Verbatim[Pattern][symbol_, "
        "pattern_?(!MatchQ[#, _Blank|_BlankSequence|_BlankNullSequence]&)]": (
            'Infix[{symbol, pattern}, ":", 150, Left]'
        )
    }
    summary_text = "a named pattern"

    def init(
        self, expr: Expression, evaluation: OptionalType[Evaluation] = None
    ) -> None:
        if len(expr.elements) != 2:
            self.error("patvar", expr)
        varname = expr.elements[0].get_name()
        if varname is None or varname == "":
            self.error("patvar", expr)
        super().init(expr, evaluation=evaluation)
        self.varname = varname
        self.pattern = BasePattern.create(expr.elements[1], evaluation=evaluation)

    def __repr__(self):
        return "<Pattern: %s>" % repr(self.pattern)

    def get_match_count(
        self, vars_dict: OptionalType[dict] = None
    ) -> Union[int, tuple]:
        return self.pattern.get_match_count(vars_dict)

    def match(self, expression: Expression, pattern_context: dict):
        """Match with a (named) pattern"""
        yield_func = pattern_context["yield_func"]
        vars_dict = pattern_context["vars_dict"]

        existing = vars_dict.get(self.varname, None)
        if existing is None:
            new_vars_dict = vars_dict.copy()
            new_vars_dict[self.varname] = expression
            pattern_context = pattern_context.copy()
            pattern_context["vars_dict"] = new_vars_dict
            # for vars_2, rest in self.pattern.match(
            #    expression, new_vars_dict, evaluation):
            #    yield vars_2, rest
            if isinstance(self.pattern, OptionsPattern):
                self.pattern.match(
                    expression=expression, pattern_context=pattern_context
                )
            else:
                self.pattern.match(
                    expression=expression, pattern_context=pattern_context
                )
        else:
            if existing.sameQ(expression):
                yield_func(vars_dict, None)

    def get_match_candidates(self, elements: tuple, pattern_context: dict) -> tuple:
        """
        Return a sub-tuple of elements that match with
        the pattern.
        Optional parameters provide information
        about the context where the elements and the
        patterns come from.
        """
        vars_dict = pattern_context.get("vars_dict", {})

        existing = vars_dict.get(self.varname, None)
        if existing is None:
            return self.pattern.get_match_candidates(elements, pattern_context)

        # Treat existing variable as verbatim
        verbatim_expr = Expression(SymbolVerbatim, existing)
        verbatim = Verbatim(verbatim_expr)
        return verbatim.get_match_candidates(elements, pattern_context)


class Optional(BinaryOperator, PatternObject):
    """

    <url>:WMA link:https://reference.wolfram.com/language/ref/Optional.html</url>

    <dl>
      <dt>'Optional[$patt$, $default$]'
      <dt>'$patt$ : $default$'
      <dd>is a pattern which matches $patt$, which if omitted
        should be replaced by $default$.
    </dl>

    >> f[x_, y_:1] := {x, y}
    >> f[1, 2]
     = {1, 2}
    >> f[a]
     = {a, 1}

    Note that '$symb$ : $patt$' represents a 'Pattern' object. However, there is no
    disambiguity, since $symb$ has to be a symbol in this case.

    >> x:_ // FullForm
     = Pattern[x, Blank[]]
    >> _:d // FullForm
     = Optional[Blank[], d]
    >> x:_+y_:d // FullForm
     = Pattern[x, Plus[Blank[], Optional[Pattern[y, Blank[]], d]]]

    's_.' is equivalent to 'Optional[s_]' and represents an optional parameter which, if omitted,
    gets its value from 'Default'.
    >> FullForm[s_.]
     = Optional[Pattern[s, Blank[]]]

    >> Default[h, k_] := k
    >> h[a] /. h[x_, y_.] -> {x, y}
     = {a, 2}
    """

    arg_counts = [1, 2]

    default_formats = False

    formats = {
        "Verbatim[Optional][pattern_Pattern, default_]": 'Infix[{HoldForm[pattern], HoldForm[default]}, ":", 140, Right]'
    }
    grouping = "Right"
    rules = {
        "MakeBoxes[Verbatim[Optional][Verbatim[Pattern][symbol_Symbol, Verbatim[_]]], f:StandardForm|TraditionalForm|InputForm|OutputForm]": 'MakeBoxes[symbol, f] <> "_."',
        "MakeBoxes[Verbatim[Optional][Verbatim[_]], f:StandardForm|TraditionalForm|InputForm|OutputForm]": '"_."',
    }
    operator = ":"
    summary_text = "an optional argument with a default value"

    def init(
        self, expr: Expression, evaluation: OptionalType[Evaluation] = None
    ) -> None:
        super().init(expr, evaluation=evaluation)
        self.pattern = BasePattern.create(expr.elements[0], evaluation=evaluation)
        if len(expr.elements) == 2:
            self.default = expr.elements[1]
        else:
            self.default = None

    def match(self, expression: Expression, pattern_context: dict):
        head = pattern_context.get("head", None)
        evaluation = pattern_context["evaluation"]
        element_index = pattern_context.get("element_index", None)
        element_count = pattern_context.get("element_count", None)
        vars_dict = pattern_context["vars_dict"]
        yield_func = pattern_context["yield_func"]

        if expression.has_form("Sequence", 0):
            if self.default is None:
                if head is None:  # head should be given by match_element!
                    default = None
                else:
                    name = head.get_name()
                    default = get_default_value(
                        name, evaluation, element_index, element_count
                    )
                if default is None:
                    evaluation.message(
                        "Pattern", "nodef", head, element_index, element_count
                    )
                    return
            else:
                default = self.default

            expression = default
        # for vars_2, rest in self.pattern.match(expression, vars_dict, evaluation):
        #    yield vars_2, rest
        self.pattern.match(
            expression,
            {
                "yield_func": yield_func,
                "vars_dict": vars_dict,
                "evaluation": evaluation,
            },
        )

    def get_match_count(self, vars_dict: OptionalType[dict] = None) -> tuple:
        return (0, 1)


def get_default_value(
    name: str,
    evaluation: Evaluation,
    k: OptionalType[int] = None,
    n: OptionalType[int] = None,
):
    """
    Get the default value associated to a name, and optionally,
    to a position in the expression.
    """
    pos = []
    if k is not None:
        pos.append(k)
    if n is not None:
        pos.append(n)
    for pos_len in reversed(range(len(pos) + 1)):
        # Try patterns from specific to general
        defaultexpr = Expression(
            SymbolDefault, Symbol(name), *[Integer(index) for index in pos[:pos_len]]
        )
        result = evaluation.definitions.get_value(
            name, "System`DefaultValues", defaultexpr, evaluation
        )
        if result is not None:
            if result.sameQ(defaultexpr):
                result = result.evaluate(evaluation)
            return result
    return None


class _Blank(PatternObject):
    arg_counts = [0, 1]

    _instance = None

    def __new__(cls, *args, **kwargs):
        if kwargs.get("expression", None) is False:
            return super().__new__(cls, *args, **kwargs)

        num_elem = len(args[0].elements)
        assert num_elem < 2, f"{cls} should have at most an element."

        if num_elem != 0:
            return super().__new__(cls, *args, **kwargs)
        # no arguments. Use the singleton
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def init(
        self, expr: Expression, evaluation: OptionalType[Evaluation] = None
    ) -> None:
        super().init(expr, evaluation=evaluation)
        if expr.elements:
            self.head = expr.elements[0]
        else:
            # FIXME: elswhere, some code wants to
            # get the attributes of head.
            # So is this really the best thing to do here?
            self.head = None


class Blank(_Blank):
    """
    <url>:WMA link:https://reference.wolfram.com/language/ref/Blank.html</url>

    <dl>
      <dt>'Blank[]'
      <dt>'_'
      <dd>represents any single expression in a pattern.
      <dt>'Blank[$h$]'
      <dt>'_$h$'
      <dd>represents any expression with head $h$.
    </dl>

    >> MatchQ[a + b, _]
     = True

    Patterns of the form '_'$h$ can be used to test the types of
    objects:
    >> MatchQ[42, _Integer]
     = True
    >> MatchQ[1.0, _Integer]
     = False
    >> {42, 1.0, x} /. {_Integer -> "integer", _Real -> "real"} // InputForm
     = {"integer", "real", x}

    'Blank' only matches a single expression:
    >> MatchQ[f[1, 2], f[_]]
     = False
    """

    rules = {
        "MakeBoxes[Verbatim[Blank][], f:StandardForm|TraditionalForm|OutputForm|InputForm]": '"_"',
        "MakeBoxes[Verbatim[Blank][head_Symbol], f:StandardForm|TraditionalForm|OutputForm|InputForm]": '"_" <> MakeBoxes[head, f]',
    }
    summary_text = "match to any single expression"

    def match(self, expression: Expression, pattern_context: dict):
        vars_dict = pattern_context["vars_dict"]
        yield_func = pattern_context["yield_func"]

        if not expression.has_form("Sequence", 0):
            if self.head is not None:
                if expression.get_head().sameQ(self.head):
                    yield_func(vars_dict, None)
            else:
                yield_func(vars_dict, None)


class BlankSequence(_Blank):
    """
    <url>:WMA link:https://reference.wolfram.com/language/ref/BlankSequence.html</url>

    <dl>
      <dt>'BlankSequence[]'
      <dt>'__'
      <dd>represents any non-empty sequence of expression elements in
        a pattern.
      <dt>'BlankSequence[$h$]'
      <dt>'__$h$'
      <dd>represents any sequence of elements, all of which have head $h$.
    </dl>

    Use a 'BlankSequence' pattern to stand for a non-empty sequence of
    arguments:
    >> MatchQ[f[1, 2, 3], f[__]]
     = True
    >> MatchQ[f[], f[__]]
     = False

    '__'$h$ will match only if all elements have head $h$:
    >> MatchQ[f[1, 2, 3], f[__Integer]]
     = True
    >> MatchQ[f[1, 2.0, 3], f[__Integer]]
     = False

    The value captured by a named 'BlankSequence' pattern is a
    'Sequence' object:
    >> f[1, 2, 3] /. f[x__] -> x
     = Sequence[1, 2, 3]
    """

    rules = {
        "MakeBoxes[Verbatim[BlankSequence][], f:StandardForm|TraditionalForm|OutputForm|InputForm]": '"__"',
        "MakeBoxes[Verbatim[BlankSequence][head_Symbol], f:StandardForm|TraditionalForm|OutputForm|InputForm]": '"__" <> MakeBoxes[head, f]',
    }
    summary_text = "match to a non-empty sequence of elements"

    def match(self, expression: Expression, pattern_context: dict):
        vars_dict = pattern_context["vars_dict"]
        yield_func = pattern_context["yield_func"]
        elements = expression.get_sequence()
        if not elements:
            return
        if self.head:
            ok = True
            for element in elements:
                if element.get_head() != self.head:
                    ok = False
                    break
            if ok:
                yield_func(vars_dict, None)
        else:
            yield_func(vars_dict, None)

    def get_match_count(self, vars_dict: OptionalType[dict] = None) -> tuple:
        return (1, None)


class BlankNullSequence(_Blank):
    """
    <url>:WMA link:https://reference.wolfram.com/language/ref/BlankNullSequence.html</url>

    <dl>
      <dt>'BlankNullSequence[]'
      <dt>'___'
      <dd>represents any sequence of expression elements in a pattern,
        including an empty sequence.
    </dl>

    'BlankNullSequence' is like 'BlankSequence', except it can match an
    empty sequence:
    >> MatchQ[f[], f[___]]
     = True
    """

    rules = {
        "MakeBoxes[Verbatim[BlankNullSequence][], f:StandardForm|TraditionalForm|OutputForm|InputForm]": '"___"',
        "MakeBoxes[Verbatim[BlankNullSequence][head_Symbol], f:StandardForm|TraditionalForm|OutputForm|InputForm]": '"___" <> MakeBoxes[head, f]',
    }
    summary_text = "match to a sequence of zero or more elements"

    def match(self, expression: Expression, pattern_context: dict):
        """Match with a BlankNullSequence"""
        vars_dict = pattern_context["vars_dict"]
        yield_func = pattern_context["yield_func"]
        elements = expression.get_sequence()
        if self.head:
            ok = True
            for element in elements:
                if element.get_head() != self.head:
                    ok = False
                    break
            if ok:
                yield_func(vars_dict, None)
        else:
            yield_func(vars_dict, None)

    def get_match_count(self, vars_dict: OptionalType[dict] = None) -> tuple:
        return (0, None)


class Repeated(PostfixOperator, PatternObject):
    """
    <url>:WMA link:https://reference.wolfram.com/language/ref/Repeated.html</url>

    <dl>
      <dt>'Repeated[$pattern$]'
      <dd>matches one or more occurrences of $pattern$.
    </dl>

    >> a_Integer.. // FullForm
     = Repeated[Pattern[a, Blank[Integer]]]
    >> 0..1//FullForm
     = Repeated[0]
    >> {{}, {a}, {a, b}, {a, a, a}, {a, a, a, a}} /. {Repeated[x : a | b, 3]} -> x
     = {{}, a, {a, b}, a, {a, a, a, a}}
    >> f[x, 0, 0, 0] /. f[x, s:0..] -> s
     = Sequence[0, 0, 0]
    """

    arg_counts = [1, 2]
    messages = {
        "range": (
            "Range specification in integers (max or {min, max}) "
            "expected at position `1` in `2`."
        )
    }

    operator = ".."
    summary_text = "match to one or more occurrences of a pattern"

    def init(
        self,
        expr: Expression,
        min_idx: int = 1,
        evaluation: OptionalType[Evaluation] = None,
    ):
        self.pattern = BasePattern.create(expr.elements[0], evaluation=evaluation)
        self.max = None
        self.min = min_idx
        if len(expr.elements) == 2:
            element_1 = expr.elements[1]
            allnumbers = not any(
                element.get_int_value() is None for element in element_1.get_elements()
            )
            if element_1.has_form("List", 1, 2) and allnumbers:
                self.max = element_1.elements[-1].get_int_value()
                self.min = element_1.elements[0].get_int_value()
            elif element_1.get_int_value():
                self.max = element_1.get_int_value()
            else:
                self.error("range", 2, expr)

    def match(self, expression: Expression, pattern_context: dict):
        """Match with Repeated[...]"""
        yield_func = pattern_context["yield_func"]
        vars_dict = pattern_context["vars_dict"]
        evaluation = pattern_context["evaluation"]
        elements = expression.get_sequence()
        if len(elements) < self.min:
            return
        if self.max is not None and len(elements) > self.max:
            return

        def iter_fn(yield_iter, rest_elements, vars_dict):
            if rest_elements:
                # for new_vars_dict, rest in self.pattern.match(rest_elements[0],
                # vars_dict, evaluation):
                def yield_match(new_vars_dict, rest):
                    # for sub_vars_dict, sub_rest in iter(rest_elements[1:],
                    #                                new_vars):
                    #    yield sub_vars_dict, rest
                    iter_fn(yield_iter, rest_elements[1:], new_vars_dict)

                self.pattern.match(
                    rest_elements[0],
                    {
                        "yield_func": yield_match,
                        "vars_dict": vars_dict,
                        "evaluation": evaluation,
                    },
                )
            else:
                yield_iter(vars_dict, None)

        # for vars_dict, rest in iter(elements, vars):
        #    yield_func(vars_dict, rest)
        iter_fn(yield_func, elements, vars_dict)

    def get_match_count(self, vars_dict: OptionalType[dict] = None) -> tuple:
        return (self.min, self.max)


class RepeatedNull(Repeated):
    """
    <url>:WMA link:https://reference.wolfram.com/language/ref/RepeatedNull.html</url>

    <dl>
      <dt>'RepeatedNull[$pattern$]'
      <dd>matches zero or more occurrences of $pattern$.
    </dl>

    >> a___Integer...//FullForm
     = RepeatedNull[Pattern[a, BlankNullSequence[Integer]]]
    >> f[x] /. f[x, 0...] -> t
     = t
    """

    operator = "..."
    summary_text = "match to zero or more occurrences of a pattern"

    def init(
        self, expr: Expression, evaluation: OptionalType[Evaluation] = None
    ) -> None:
        super().init(expr, min_idx=0, evaluation=evaluation)


class Shortest(Builtin):
    """
    <url>:WMA link:https://reference.wolfram.com/language/ref/Shortest.html</url>

    <dl>
      <dt>'Shortest[$pat$]'
      <dd>is a pattern object that matches the shortest sequence consistent with the pattern $p$.
    </dl>

    >> StringCases["aabaaab", Shortest["a" ~~ __ ~~ "b"]]
     =  {aab, aaab}

    >> StringCases["aabaaab", Shortest[RegularExpression["a+b"]]]
     = {aab, aaab}
    """

    summary_text = "the shortest part matching a string pattern"


class Longest(Builtin):
    """
    <url>
    :WMA link:
    https://reference.wolfram.com/language/ref/Longest.html</url>

    <dl>
      <dt>'Longest[$pat$]'
      <dd>is a pattern object that matches the longest sequence consistent \
      with the pattern $p$.
    </dl>

    >> StringCases["aabaaab", Longest["a" ~~ __ ~~ "b"]]
     = {aabaaab}

    >> StringCases["aabaaab", Longest[RegularExpression["a+b"]]]
     = {aab, aaab}
    """

    summary_text = "the longest part matching a string pattern"


class Condition(BinaryOperator, PatternObject):
    """
    <url>
    :WMA link:
    https://reference.wolfram.com/language/ref/Condition.html</url>

    <dl>
      <dt>'Condition[$pattern$, $expr$]'
      <dt>'$pattern$ /; $expr$'
      <dd>places an additional constraint on $pattern$ that only
        allows it to match if $expr$ evaluates to 'True'.
    </dl>

    The controlling expression of a 'Condition' can use variables from
    the pattern:
    >> f[3] /. f[x_] /; x>0 -> t
     = t
    >> f[-3] /. f[x_] /; x>0 -> t
     = f[-3]

    'Condition' can be used in an assignment:
    >> f[x_] := p[x] /; x>0
    >> f[3]
     = p[3]
    >> f[-3]
     = f[-3]
    """

    arg_counts = [2]
    # Don't know why this has attribute HoldAll in Mathematica
    attributes = A_HOLD_REST | A_PROTECTED
    operator = "/;"
    summary_text = "conditional definition"

    def init(
        self, expr: Expression, evaluation: OptionalType[Evaluation] = None
    ) -> None:
        super().init(expr, evaluation=evaluation)
        self.test = expr.elements[1]
        # if (expr.elements[0].get_head_name() == "System`Condition" and
        #    len(expr.elements[0].elements) == 2):
        #    self.test = Expression(SymbolAnd, self.test, expr.elements[0].elements[1])
        #    self.pattern = BasePattern.create(expr.elements[0].elements[0])
        # else:
        self.pattern = BasePattern.create(expr.elements[0], evaluation=evaluation)

    def match(self, expression: Expression, pattern_context: dict):
        """Match with Condition pattern"""
        # for new_vars_dict, rest in self.pattern.match(expression, vars_dict,
        # evaluation):
        evaluation = pattern_context["evaluation"]
        yield_func = pattern_context["yield_func"]

        def yield_match(new_vars_dict, rest):
            test_expr = self.test.replace_vars(new_vars_dict)
            test_result = test_expr.evaluate(evaluation)
            if test_result is SymbolTrue:
                yield_func(new_vars_dict, rest)

        pattern_context = pattern_context.copy()
        pattern_context["yield_func"] = yield_match
        self.pattern.match(expression, pattern_context)


class OptionsPattern(PatternObject):
    """
    <url>
    :WMA link:
    https://reference.wolfram.com/language/ref/OptionsPattern.html</url>

    <dl>
      <dt>'OptionsPattern[$f$]'
      <dd>is a pattern that stands for a sequence of options given \
        to a function, with default values taken from 'Options[$f$]'. \
        The options can be of the form '$opt$->$value$' or
        '$opt$:>$value$', and might be in arbitrarily nested lists.

      <dt>'OptionsPattern[{$opt1$->$value1$, ...}]'
      <dd>takes explicit default values from the given list. The
        list may also contain symbols $f$, for which 'Options[$f$]' is \
        taken into account; it may be arbitrarily nested. \
        'OptionsPattern[{}]' does not use any default values.
    </dl>

    The option values can be accessed using 'OptionValue'.

    >> f[x_, OptionsPattern[{n->2}]] := x ^ OptionValue[n]
    >> f[x]
     = x ^ 2
    >> f[x, n->3]
     = x ^ 3

    Delayed rules as options:
    >> e = f[x, n:>a]
     = x ^ a
    >> a = 5;
    >> e
     = x ^ 5

    Options might be given in nested lists:
    >> f[x, {{{n->4}}}]
     = x ^ 4
    """

    arg_counts = [0, 1]
    summary_text = "a sequence of optional named arguments"

    def init(
        self, expr: Expression, evaluation: OptionalType[Evaluation] = None
    ) -> None:
        super().init(expr, evaluation=evaluation)
        try:
            self.defaults = expr.elements[0]
        except IndexError:
            # OptionsPattern[] takes default options of the nearest enclosing
            # function. Set to not None in self.match
            self.defaults = None

    def match(self, expression: Expression, pattern_context: dict):
        """Match with an OptionsPattern"""
        head = pattern_context.get("head", None)
        evaluation = pattern_context["evaluation"]
        if self.defaults is None:
            self.defaults = head
            if self.defaults is None:
                # we end up here with OptionsPattern that do not have any
                # default options defined, e.g. with this code:
                # f[x:OptionsPattern[]] := x; f["Test" -> 1]
                # set self.defaults to an empty List, so we don't crash.
                self.defaults = ListExpression()
        defaults = self.defaults
        values = (
            defaults.get_option_values(
                evaluation, allow_symbols=True, stop_on_error=False
            )
            if isinstance(defaults, EvalMixin)
            else {}
        )
        sequence = expression.get_sequence()
        for options in sequence:
            option_values = (
                options.get_option_values(evaluation)
                if isinstance(options, EvalMixin)
                else None
            )
            if option_values is None:
                return
            values.update(option_values)
        new_vars_dict = pattern_context["vars_dict"].copy()
        for name, value in values.items():
            new_vars_dict["_option_" + name] = value
        pattern_context["yield_func"](new_vars_dict, None)

    def get_match_count(self, vars_dict: OptionalType[dict] = None) -> tuple:
        return (0, None)

    def get_match_candidates(
        self, elements: Tuple[BaseElement], pattern_context: dict
    ) -> tuple:
        """
        Return the sub-tuple of elements that matches with the pattern.
        """

        def _match(element: Expression):
            return element.has_form(("Rule", "RuleDelayed"), 2) or element.has_form(
                "List", None
            )

        return tuple((element for element in elements if _match(element)))


class Dispatch(Atom):
    class_head_name = "System`Dispatch"

    def __init__(self, rulelist: Expression, evaluation: Evaluation) -> None:
        self.src = ListExpression(*rulelist)
        self.rules = [Rule(rule.elements[0], rule.elements[1]) for rule in rulelist]
        self._elements = None
        self._head = SymbolDispatch

    def get_sort_key(self, pattern_sort: bool = False) -> tuple:
        return self.src.get_sort_key()

    def get_atom_name(self):
        return "System`Dispatch"

    def __repr__(self):
        return "dispatch"

    def atom_to_boxes(self, f: Symbol, evaluation: Evaluation):
        from mathics.builtin.box.layout import RowBox
        from mathics.eval.makeboxes import format_element

        box_element = format_element(self.src, evaluation, f)
        return RowBox(String("Dispatch"), String("["), box_element, String("]"))


class DispatchAtom(AtomBuiltin):
    """
    <url>
    :WMA link:
    https://reference.wolfram.com/language/ref/DispatchAtom.html</url>

    <dl>
      <dt>'Dispatch[$rulelist$]'
      <dd>Introduced for compatibility. Currently, it just return $rulelist$. \
          In the future, it should return an optimized DispatchRules atom, \
          containing an optimized set of rules.
    </dl>

    >> rules = {{a_,b_}->a^b, {1,2}->3., F[x_]->x^2};
    >> F[2] /. rules
     = 4
    >> dispatchrules = Dispatch[rules]
     =  Dispatch[{{a_, b_} -> a ^ b, {1, 2} -> 3., F[x_] -> x ^ 2}]
    >>  F[2] /. dispatchrules
     = 4
    """

    class_head_name = "System`DispatchAtom"
    messages = {
        "invrpl": "`1` is not a valid rule or list of rules.",
    }
    summary_text = "convert a list of rules in an optimized dispatch rules atom"

    def __repr__(self):
        return "dispatchatom"

    def eval_create(
        self, rules: ListExpression, evaluation: Evaluation
    ) -> OptionalType[BaseElement]:
        """Dispatch[rules_List]"""
        # TODO:
        # The next step would be to enlarge this method, in order to
        # check that all the elements in x are rules, eliminate redundancies
        # in the list, and sort the list in a way that increases efficiency.
        # A second step would be to implement an ``Atom`` class containing the
        # compiled patterns, and modify Replace and ReplaceAll to handle this
        # kind of objects.
        #
        if isinstance(rules, Dispatch):
            return rules
        if isinstance(rules, Symbol):
            rules = rules.evaluate(evaluation)

        if rules.has_form("List", None):
            rules = rules.elements
        else:
            rules = [rules]

        all_list = all(rule.has_form("List", None) for rule in rules)
        if all_list:
            elements = [self.eval_create(rule, evaluation) for rule in rules]
            return ListExpression(*elements)
        flatten_list = []
        for rule in rules:
            if isinstance(rule, Symbol):
                rule = rule.evaluate(evaluation)
            if rule.has_form("List", None):
                flatten_list.extend(rule.elements)
            elif rule.has_form(("Rule", "RuleDelayed"), 2):
                flatten_list.append(rule)
            elif isinstance(rule, Dispatch):
                flatten_list.extend(rule.src.elements)
            else:
                # WMA does not raise this message: just leave it unevaluated,
                # and raise an error when the dispatch rule is used.
                evaluation.message("Dispatch", "invrpl", rule)
                return None
        try:
            return Dispatch(flatten_list, evaluation)
        except Exception:
            return None

    def eval_normal(self, dispatch: Dispatch, evaluation: Evaluation) -> ListExpression:
        """Normal[dispatch_Dispatch]"""
        if isinstance(dispatch, Dispatch):
            return dispatch.src
        return dispatch.elements[0]
