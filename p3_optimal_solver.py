#!/usr/bin/python
# ---------------------------------------------------------------------------
# File: p3_optimal_solver.py
# Version todo
# ---------------------------------------------------------------------------
#
# ---------------------------------------------------------------------------
"""
"""
import random
import docplex.mp.model as cpx
import cplex
from cplex.exceptions import CplexError
import time
import networkx as nx
from networkx.algorithms import bipartite
import bellmanford as bf
from networkx.readwrite import json_graph
import json

# Tutorial: https://medium.com/opex-analytics/optimization-modeling-in-python-pulp-gurobi-and-cplex-83a62129807a

def merge_two_dicts(x, y):
    z = x.copy()   # start with x's keys and values
    z.update(y)    # modifies z with y's keys and values & returns None
    return z

def solving_placement_problem(set_PM, set_state, set_nf, s, c, d, e_r, M):
    opt_model = cpx.Model(name="P3")

    # Binary variables
    x_vars = {(i, u): opt_model.binary_var(name="x_{0}_{1}".format(i, u)) for i in set_PM for u in set_state}

    # == constraints
    mapping_constraints = {}
    for u in set_state:
        c_name = "c1_{}".format(u)
        tmp_constraints = { c_name : opt_model.add_constraint(ct=opt_model.sum(x_vars[i, u] for i in set_PM) == 1, ctname=c_name)}
        mapping_constraints = merge_two_dicts(tmp_constraints, mapping_constraints)

    # <= constraints
    capacity_constraints = {}
    for i in set_PM:
        c_name = "c2_{}".format(i)
        tmp_constraints = {c_name: opt_model.add_constraint(ct=opt_model.sum(s[u] * x_vars[i, u] for u in set_state) <= c[i], ctname=c_name)}
        capacity_constraints = merge_two_dicts(tmp_constraints, capacity_constraints)

    constraints = merge_two_dicts(mapping_constraints, capacity_constraints)

    # objective
    """
    for i in set_PM:
        for u in set_state:
            for v in set_nf:
                print "x_{0}_{1} * e_{1}_{2} * d_{0}_{3} <--------> x_{0}_{1} * {4} * {5}".format(i,u,v,M[v], e_r[u,v], d[i,M[v]])
    """

    objective = opt_model.sum(x_vars[i, u] * e_r[u,v] * d[i,M[v]] for i in set_PM for u in set_state for v in set_nf)

    # for minimization
    opt_model.minimize(objective)

    opt_model.export_as_lp(basename="p3", path=".")

    # solving with local cplex
    asd = opt_model.solve()

    print(asd)

    import pandas as pd
    opt_df = pd.DataFrame.from_dict(x_vars, orient="index", columns = ["variable_object"])
    opt_df.index = pd.MultiIndex.from_tuples(opt_df.index,names=["column_i", "column_j"])

    opt_df["solution_value"] = opt_df["variable_object"].apply(lambda item: item.solution_value)

    opt_df.drop(columns=["variable_object"], inplace=True)
    opt_df.to_csv("./optimization_solution.csv")


