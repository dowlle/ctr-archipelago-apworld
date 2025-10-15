import ast
import operator
from BaseClasses import CollectionState
import logging

# --- Allowed operators and AST visitors for safety ---
OPS = {
    ast.And: operator.and_,
    ast.Or: operator.or_,
    ast.Not: operator.not_
}

COMPARISONS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le
}


class SafeLogicEvaluator(ast.NodeVisitor):
    """
    Safely evaluates a limited subset of Python expressions for logic rules.
    Supports: has('Item', n), and/or/not, comparisons, True/False, numbers.
    """

    def __init__(self, state, player):
        self.state = state
        self.player = player

    def visit_BoolOp(self, node):
        op_type = type(node.op)
        if op_type not in OPS:
            raise ValueError(f"Unsupported BoolOp {op_type}")
        values = [self.visit(v) for v in node.values]
        result = values[0]
        for v in values[1:]:
            result = OPS[op_type](result, v)
        return result

    def visit_UnaryOp(self, node):
        if isinstance(node.op, ast.Not):
            return operator.not_(self.visit(node.operand))
        raise ValueError(f"Unsupported unary op {type(node.op)}")

    def visit_Compare(self, node):
        left = self.visit(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            if type(op) not in COMPARISONS:
                raise ValueError(f"Unsupported comparison {type(op)}")
            right = self.visit(comparator)
            if not COMPARISONS[type(op)](left, right):
                return False
        return True

    def visit_NameConstant(self, node):
        return node.value

    def visit_Constant(self, node):
        return node.value

    def visit_Name(self, node):
        if node.id in ("True", "always"):
            return True
        elif node.id == "False":
            return False
        raise ValueError(f"Unknown identifier {node.id}")

    def visit_Call(self, node):
        if not isinstance(node.func, ast.Name) or node.func.id != "has":
            raise ValueError(f"Unsupported function {node.func.id if isinstance(node.func, ast.Name) else node.func}")

        args = [self.visit(a) for a in node.args]
        if not args:
            raise ValueError("has() requires at least one argument")

        item = args[0]
        count = args[1] if len(args) > 1 else 1
        return self.state.has(item, self.player, count)

    def generic_visit(self, node):
        raise ValueError(f"Unsupported syntax: {ast.dump(node)}")


def parse_rule_expression(expr):
    """Parse an expression string into an AST node safely."""
    try:
        return ast.parse(expr, mode="eval").body
    except Exception as e:
        raise ValueError(f"Invalid rule expression: {expr}\n{e}")


def make_rule(expr_text, player, multiworld):
    """
    Returns a callable(state) that evaluates a logic expression safely.
    """
    expr_text = expr_text.strip()
    if not expr_text or expr_text.lower() in ("true", "always"):
        return lambda state: True

    node = parse_rule_expression(expr_text)

    def rule(state):
        evaluator = SafeLogicEvaluator(state, player)
        try:
            return evaluator.visit(node)
        except Exception as e:
            print(f"[Rule Parse Error] {expr_text} => {e}")
            return False

    return rule


def set_rules(world):
    """
    Assign parsed logic rules to all entrances and locations from JSON.
    """
    player, mw = world.player, world.multiworld

    for region in mw.get_regions(player):
        # Entrances
        for ent in region.exits:
            rule_text = getattr(ent, "access_rule_text", "True")
            ent.access_rule = make_rule(rule_text, player, mw)
        # Locations
        for loc in region.locations:
            rule_text = getattr(loc, "logic_text", "True")
            loc.access_rule = make_rule(rule_text, player, mw)

def add_time_trial_and_ctr_requirements(world, player):
    """Lock Time Trials and CTR Challenges until Trophy Race of same track is complete,
    but skip bonus tracks (e.g. Slide Coliseum, Turbo Track) without Trophy Races."""
    mw = world.multiworld

    all_location_names = {loc.name for loc in mw.get_locations(player)}

    for loc in mw.get_locations(player):
        name = loc.name

        if not (name.endswith("Time Trial") or name.endswith("CTR Token Challenge")):
            continue

        track_prefix = name.split(":")[0].strip()
        trophy_name = f"{track_prefix}: Trophy Race"

        if trophy_name not in all_location_names:
            logging.debug(f"[CTR Rules] Skipping prerequisite for {name} (no Trophy Race found)")
            continue

        def make_rule_for_trophy(trophy_name=trophy_name, player=player):
            def rule(state: CollectionState):
                return state.can_reach(trophy_name, "Location", player)
            return rule

        loc.access_rule = make_rule_for_trophy()
        logging.debug(f"[CTR Rules] Added Trophy prerequisite: {name} requires {trophy_name}")