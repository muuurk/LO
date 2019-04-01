#!/usr/bin/python
# ---------------------------------------------------------------------------
# File: p5_optimal_solver.py
# Version todo
# ---------------------------------------------------------------------------
#
# ---------------------------------------------------------------------------
"""
Tutorial: https://medium.com/opex-analytics/optimization-modeling-in-python-pulp-gurobi-and-cplex-83a62129807a
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
import datetime
import os.path
from docloud.job import JobClient
import itertools
import matplotlib.pyplot as plt
import sys
import datetime


def merge_two_dicts(x, y):
    z = x.copy()  # start with x's keys and values
    z.update(y)  # modifies z with y's keys and values & returns None
    return z


def read_json_file(filename):
    with open(filename) as f:
        js_graph = json.load(f)
    return json_graph.node_link_graph(js_graph)


def generating_delay_matrix(graph):
    d = {(i, j): 1000000 for i in list(graph.nodes) for j in list(graph.nodes)}
    for i in list(graph.nodes):
        for j in list(graph.nodes):
            path_length, path_nodes, negative_cycle = bf.bellman_ford(graph, source=i, target=j, weight="delay")
            d[(i, j)] = path_length
    return d


def generating_req_adj(states, nfs_n_replicas, graph):
    adj = {(j, i): 0 for j in list(states + nfs_n_replicas) for i in list(states + nfs_n_replicas)}
    for i in list(states + nfs_n_replicas):
        for j in list(states + nfs_n_replicas):
            try:
                # FIXME
                graph[i][j]
                adj[(i, j)] = 1
            except:
                pass
    return adj


def generating_nf_mapping_matrix(graph):
    m = {}
    for i in list(graph.nodes):
        for j in graph.nodes[i]['NFs']:
            m = merge_two_dicts(m, {j: i})
    return m


def get_NF_of_state(graph, state):
    neighbours = [n for n in graph.neighbors(state)]
    vnfs = []
    if neighbours == []:
        raise Exception("Node '{}' is not linked to any of the virtual nodes in the requested graph".format(state))
    else:
        for node in neighbours:
            if "function" in node:
                vnfs.append(node)
        return vnfs


def generating_AA(states, G_request):
    AA = []
    for s in states:
        if G_request.nodes[s]["replicas"] != []:
            if len(G_request.nodes[s]["replicas"]) > 1:
                AA.extend(list(itertools.combinations(G_request.nodes[s]["replicas"], 2)))
            for r in G_request.nodes[s]["replicas"]:
                AA.append((s, r))
    return AA


def is_OL(u, v, OL):
    for i in OL:
        for original_link, replica_links in i.items():
            if (u, v) == original_link:
                return True
            elif (u, v) in replica_links:
                return True
    return False


def exist_reading_link(u, v, graph):
    try:
        graph[u][v]
        return True
    except:
        return False


def generating_OL(states, nfs, replicas, G_request):
    OL = []
    for s in states:
        if G_request.nodes[s]["replicas"] != []:
            for n in nfs:
                if exist_reading_link(s, n, G_request):
                    OL.append({(s, n): [(r, n) for r in G_request.nodes[s]["replicas"]]})
    return OL


def get_OLs(u, v, OL):
    for i in OL:
        for original_link, replica_links in i.items():
            if (u, v) == original_link:
                return [(u, v)] + replica_links
            elif (u, v) in replica_links:
                tmp = ([original_link] + replica_links)
                return tmp
    return False


def solving_placement_problem_from_file(topology_graph, request_graph, test_num):
    if not os.path.isfile("./cplex_models/p5_cplex_model_{}.lp".format(test_num)):

        # Reading networkx file
        G_topology = read_json_file(topology_graph)
        G_request = read_json_file(request_graph)

        set_PM = list(G_topology.nodes)
        set_state_or_nf = list(G_request.nodes)
        set_state, set_nf, set_replica = [], [], []
        for i in set_state_or_nf:
            if "function" in i:
                set_nf.append(i)
            elif "state" in i:
                set_state.append(i)
            elif "replica" in i:
                set_replica.append(i)
        # TODO: Validating request graph
        for i in set_state:
            try:
                G_request.nodes[i]['size']
            except:
                RuntimeError("The given request graph is incorrect: State {} has no 'size' value".format(i))

        s = {i: G_request.nodes[i]['size'] for i in set_state + set_replica}
        c = {i: G_topology.nodes[i]['capacity'] for i in set_PM}
        print("Generating delay matrix...")
        d = generating_delay_matrix(G_topology)
        print("Generating state-function adjacency matrix...")
        e_r = generating_req_adj(set_state, set_nf + set_replica, G_request)
        print("Generating Function mapping matrix...")
        M = generating_nf_mapping_matrix(G_topology)
        print("Generating Anti-Affinity set")
        AA = generating_AA(set_state, G_request)
        print("Generating OR-Link set")
        OL = generating_OL(set_state, set_nf, set_replica, G_request)

        opt_model = cpx.Model(name="P5")

        # Binary variables
        print("Creating variables 1...")
        x_vars = {(i, u): opt_model.binary_var(name="x_({0},{1})".format(i, u)) for i in set_PM for u in
                  set_state + set_replica + set_nf}

        for i in set_PM:
            for u in set_state + set_replica + set_nf:
                print("x_({0},{1})".format(i, u))

        print("\nCreating variables 2...")
        index_set = set()
        for i in set_PM:
            for u in set_state + set_replica + set_nf:
                index_set.add((i, u))
        index_combinations = list(itertools.permutations(index_set, 2))
        y_vars = {
            (i[0], i[1], j[0], j[1]): opt_model.binary_var(name="y_({},{})_({},{})".format(i[0], i[1], j[0], j[1])) for
        i, j
            in index_combinations}

        print("\nCreating variables 3...")
        index_permutations = list(itertools.permutations((set_state + set_nf + set_replica), 2))
        z_vars = {(u, v): opt_model.binary_var(name="z_({},{})".format(u, v)) for u, v in index_permutations}

        for u, v in index_permutations:
            print("z_({},{})".format(u, v))

        # == constraints
        print("\nCreating constraints 1 - virtual element can be mapped into only one server")
        for u in set_state + set_replica:
            c_name = "c1_{}".format(u)
            opt_model.add_constraint(ct=opt_model.sum(x_vars[i, u] for i in set_PM) == 1, ctname=c_name)

        for u in set_state + set_replica:
            for i in set_PM:
                sys.stdout.write("x_vars[{}, {}] + ".format(i, u))
            print("== 1")

        # <= constraints
        print("\nCreating constraints 2 - server capacity constraint")
        for i in set_PM:
            c_name = "c2_{}".format(i)
            opt_model.add_constraint(ct=opt_model.sum(s[u] * x_vars[i, u] for u in set_state + set_replica) <= c[i],
                                     ctname=c_name)

        for i in set_PM:
            for u in set_state + set_replica:
                sys.stdout.write("x_vars[{}, {}] + ".format(i, u))
            print("<= {}".format(c[i]))

        # <= constraints
        print("\nCreating constraints 3 - anti-affinity rules")
        for i in set_PM:
            if "server" in i:
                # print("\nSERVER: {}".format(i))
                for u, v in AA:
                    c_name = "c3_{}_n){}_in_{}".format(u, v, i)
                    opt_model.add_constraint(ct=(x_vars[i, u] + x_vars[i, v]) <= 1, ctname=c_name)

        for i in set_PM:
            if "server" in i:
                # print("\nSERVER: {}".format(i))
                for u, v in AA:
                    print("x_vars[{},{}] + x_vars[{},{}]) <= 1".format(i, u, i, v))

        # == constraints
        print("\nCreating constraints 4 - NFs running places")
        for function in set_nf:
            for server in set_PM:
                c_name = "c4_{}_in_{}".format(function, server)
                try:
                    if M[function] == server:
                        opt_model.add_constraint(ct=x_vars[server, function] == 1, ctname=c_name)
                        print("x_vars[{}, {}] == 1".format(server, function))
                    else:
                        opt_model.add_constraint(ct=x_vars[server, function] == 0, ctname=c_name)
                        print("x_vars[{}, {}] == 0".format(server, function))
                except:
                    opt_model.add_constraint(ct=x_vars[server, function] == 0, ctname=c_name)
                    print("x_vars[{}, {}] == 0".format(server, function))

        # >= constraints
        print("\nCreating constraints 5 - QP -> ILP transformation constraints")

        index_set = set()
        for i in set_PM:
            for u in set_state + set_replica + set_nf:
                index_set.add((i, u))
        index_combinations = list(itertools.permutations(index_set, 2))

        for i, j in index_combinations:
            c_name = "c5_({},{})_({},{})_0".format(i[0], i[1], j[0], j[1])
            opt_model.add_constraint(ct=y_vars[i[0], i[1], j[0], j[1]] >= 0, ctname=c_name)
            c_name = "c5_({},{})_({},{})_1".format(i[0], i[1], j[0], j[1])
            opt_model.add_constraint(ct=y_vars[i[0], i[1], j[0], j[1]] >= (x_vars[i[0], i[1]] + x_vars[j[0], j[1]] -1), ctname=c_name)


        # for pm_i in set_PM:
        #     for j in range(set_PM.index(pm_i), len(set_PM)):
        #         pm_j = set_PM[j]
        #         for u in set_state:
        #             for v in set_replica + set_nf:
        #                 c_name = "c5_({},{})_({},{})_0".format(pm_i, u, pm_j, v)
        #                 opt_model.add_constraint(ct=y_vars[pm_i, u, pm_j, v] >= 1, ctname=c_name)
        #                 print("y_vars[{}, {}, {}, {}] >= 1".format(pm_i, u, pm_j, v))
        #                 c_name = "c5_({},{})_({},{})_1".format(pm_i, u, pm_j, v)
        #                 opt_model.add_constraint(ct=y_vars[pm_i, u, pm_j, v] >= x_vars[pm_i, u] + x_vars[pm_j, v] - 1,
        #                                          ctname=c_name)
        #                 print("y_vars[{}, {}, {}, {}] >= x_vars[{}, {}] + x_vars[{}, {}] - 1".format(pm_i, u, pm_j, v,
        #                                                                                              pm_i, u, pm_j, v))

        print("\nCreating constraints 6 - z variable rules")
        for u in (set_state + set_nf + set_replica):
            for v in (set_state + set_nf + set_replica):
                if u != v:
                    if is_OL(u, v, OL):
                        c_name = "c6_({},{})".format(u, v)
                        opt_model.add_constraint(
                            ct=opt_model.sum(z_vars[(i, j)] for i, j in get_OLs(u, v, OL)) == 1, ctname=c_name)
                    else:
                        c_name = "c7_({},{})".format(u, v)
                        if "function" in u and "replica" in v:
                            opt_model.add_constraint(ct=z_vars[(u, v)] == 0, ctname=c_name)
                        elif "replica" in u and "state" in v:
                            print("z_vars[({}, {})] == 0".format(u, v))
                        else:
                            opt_model.add_constraint(ct=z_vars[(u, v)] == 1, ctname=c_name)

        for u in (set_state + set_nf + set_replica):
            for v in (set_state + set_nf + set_replica):
                if u != v:
                    if is_OL(u, v, OL):
                        for i, j in get_OLs(u, v, OL):
                            sys.stdout.write("z_vars[({}, {})] + ".format(i, j))
                        print("== 1")
                    else:
                        if "function" in u and "replica" in v:
                            print("z_vars[({}, {})] == 0".format(u, v))
                        elif "replica" in u and "state" in v:
                            print("z_vars[({}, {})] == 0".format(u, v))
                        else:
                            print("z_vars[({}, {})] == 1".format(u, v))

        print("\nCreating Objective function...")
        print(datetime.datetime.now())

        servers = [i for i in set_PM if "server" in i]
        server_permutations = list(itertools.permutations(servers, 2))
        # objective = opt_model.sum(
        #     y_vars[i, u, j, v] * e_r[u, v] * d[i, j] * z_vars[u, v] for i, j in server_permutations for u, v in
        #     list(itertools.permutations(set_state + set_replica + set_nf, 2)))

        objective = opt_model.sum(
            y_vars[i, u, j, v] * e_r[u, v] * d[i, j] * z_vars[u, v] for i, j in server_permutations for u, v in
            list(itertools.permutations(set_state + set_replica + set_nf, 2)))

        # for minimization
        opt_model.minimize(objective)

        print("Exporting the problem")
        opt_model.export_as_lp(basename="p5_cplex_model_{}".format(test_num), path="./cplex_models")

        # solving with local cplex
        # print("Solving the problem locally")
        # print(datetime.datetime.now())
        # asd = opt_model.solve()

        # solving in the docplex cloud
        print("Solving the problem by the cloud")
    print(datetime.datetime.now())

    if not os.path.isfile("optimization_results/p5_cplex_result_{}.json".format(test_num)):
        client = JobClient("https://api-oaas.docloud.ibmcloud.com/job_manager/rest/v1/",
                           "api_e7f3ec88-92fd-4432-84d7-f708c4a33132")
        print(
            "You can check the status of the problem procesing here: https://dropsolve-oaas.docloud.ibmcloud.com/dropsolve")
        resp = client.execute(input=["./cplex_models/p5_cplex_model_{}.lp".format(test_num)],
                              output="optimization_results/p5_cplex_result_{}.json".format(test_num))
        # resp = opt_model.solve(url="https://api-oaas.docloud.ibmcloud.com/job_manager/rest/v1/", key="api_e7f3ec88-92fd-4432-84d7-f708c4a33132")

        if resp.job_info["solveStatus"] == "INFEASIBLE_SOLUTION":
            print("There is no valid mapping!")
            return 0
        else:
            with open("./optimization_results/p5_cplex_result_{}.json".format(test_num)) as f:
                result = json.load(f)
                for i in result["CPLEXSolution"]["variables"]:
                    if ("x_" in i["name"]) and i["value"] == str(1):
                        print("{} = 1".format(i["name"]))
            print("*** Delay cost: {} ***".format(result["CPLEXSolution"]["header"]["objectiveValue"]))
            return result["CPLEXSolution"]["header"]["objectiveValue"]
    else:
        with open("./optimization_results/p5_cplex_result_{}.json".format(test_num)) as f:
            result = json.load(f)
            for i in result["CPLEXSolution"]["variables"]:
                if ("x_" in i["name"]) and i["value"] == str(1):
                    print("{} = 1".format(i["name"]))
            print("*** Delay cost: {} ***".format(result["CPLEXSolution"]["header"]["objectiveValue"]))
            return result["CPLEXSolution"]["header"]["objectiveValue"]
