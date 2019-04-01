#!/usr/bin/python
# ---------------------------------------------------------------------------
# File: p3.py
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
import datetime
import subprocess
import csv
import os
import matplotlib.pyplot as plt
import itertools

import p3_greedy_solver
import p3_optimal_solver
import p3_heuristic_solver
import p5_optimal_solver
import p5_greedy_solver


def merge_two_dicts(x, y):
    z = x.copy()  # start with x's keys and values
    z.update(y)  # modifies z with y's keys and values & returns None
    return z


def generating_delay_matrix(graph):
    d = {}
    for i in list(graph.nodes):
        for j in list(graph.nodes):
            path_length, path_nodes, negative_cycle = bf.bellman_ford(graph, source=i, target=j, weight="delay")
            d = merge_two_dicts(d, {(i, j): path_length})
    return d


def generating_req_adj(nfs, states, graph):
    adj = {}
    for i in list(states):
        for j in list(nfs):
            try:
                graph[j][i]
                adj = merge_two_dicts(adj, {(j, i): 1})
            except:
                adj = merge_two_dicts(adj, {(j, i): 0})
    return adj


def generating_nf_mapping_matrix(graph):
    m = {}
    for i in list(graph.nodes):
        for j in graph.nodes[i]['NFs']:
            m = merge_two_dicts(m, {j: i})
    return m


def create_test_topology(test_num, exporting, problem_id):
    ### Generating topology graph ############################

    G_topology = nx.Graph()

    # Vertices

    G_topology.add_node("server_1", capacity=4, NFs=["function_1"])
    G_topology.add_node("server_2", capacity=5, NFs=[])
    G_topology.add_node("server_3", capacity=6, NFs=[])
    G_topology.add_node("server_4", capacity=3, NFs=["function_2"])

    """
    G_topology.add_node("PM1", capacity=random.randint(1, 5), NFs=["function_1"])
    G_topology.add_node("PM2", capacity=random.randint(1, 5), NFs=[])
    G_topology.add_node("PM3", capacity=random.randint(1, 5), NFs=[])
    G_topology.add_node("PM4", capacity=random.randint(1, 5), NFs=["function_2"])
    """
    # Edges

    G_topology.add_edges_from([('server_1', 'server_2', {'delay': 2}),
                               ('server_1', 'server_3', {'delay': 3}),
                               ('server_2', 'server_3', {'delay': 4}),
                               ('server_2', 'server_4', {'delay': 5})])

    """
    G_topology.add_edges_from([('PM1', 'PM2', {'delay': random.randint(1, 5)}),
                               ('PM1', 'PM3', {'delay': random.randint(1, 5)}),
                               ('PM2', 'PM3', {'delay': random.randint(1, 5)}),
                               ('PM2', 'PM4', {'delay': random.randint(1, 5)}),
                               ('PM3', 'PM4', {'delay': random.randint(1, 5)})])
    """

    # Exporting
    if exporting:
        topology_json = json_graph.node_link_data(G_topology)
        with open('graph_models/p{}_topology_graph_{}.json'.format(problem_id, test_num), 'w') as outfile:
            json.dump(topology_json, outfile)

    ### Generating request graph ############################

    G_request = nx.DiGraph()

    # Vertices

    G_request.add_nodes_from([('state_1', {'size': 1, 'replicas': []}),
                              ('state_2', {'size': 2, 'replicas': []}),
                              ('state_3', {'size': 2, 'replicas': ['replica_1']}),
                              ('state_4', {'size': 1, 'replicas': ['replica_2', 'replica_3']}),
                              ('replica_1', {'size': 2}),
                              ('replica_2', {'size': 1}),
                              ('replica_3', {'size': 1})])

    # G_request.add_nodes_from([('state_1', {'size': 1, 'replicas': []}),
    #                           ('state_2', {'size': 2, 'replicas': []}),
    #                           ('state_3', {'size': 2, 'replicas': []}),
    #                           ('state_4', {'size': 1, 'replicas': []})])

    """
    G_request.add_nodes_from([('state_1', {'size': random.randint(1, 3)}),
                              ('state_2', {'size': random.randint(1, 3)}),
                              ('state_3', {'size': random.randint(1, 3)}),
                              ('state_4', {'size': random.randint(1, 3)})],
                             bipartite=0)
    """
    G_request.add_nodes_from(['function_1', 'function_2'])

    # Edges
    G_request.add_edges_from(
        [('state_1', 'function_1'),
         ('state_2', 'function_1'),
         ('function_1', 'state_3'),
         ('state_3', 'replica_1'),
         ('state_3', 'function_2'),
         ('replica_1', 'function_2'),
         ('state_4', 'function_2'),
         ('function_2', 'state_4'),
         ('state_4', 'replica_2'),
         ('state_4', 'replica_3'),
         ('replica_2', 'function_2'),
         ('replica_3', 'function_2')
         ])

    # G_request.add_edges_from(
    #     [('state_1', 'function_1'),
    #      ('state_2', 'function_1'),
    #      ('function_1', 'state_3'),
    #      ('state_3', 'function_2'),
    #      ('state_4', 'function_2'),
    #      ('function_2', 'state_4')
    #      ])

    # Exporting
    if exporting:
        request_json = json_graph.node_link_data(G_request)
        with open('graph_models/p{}_request_graph_{}.json'.format(problem_id, test_num), 'w') as outfile:
            json.dump(request_json, outfile)

    G_topology.number_of_nodes()
    G_topology.number_of_edges()
    list(G_topology.nodes)
    list(G_topology.edges)

    # nx.draw(G_topology, with_labels=True)
    # plt.show()
    #
    # nx.draw(G_request, with_labels=True)
    # plt.show()


def read_json_file(filename):
    with open(filename) as f:
        js_graph = json.load(f)
    return json_graph.node_link_graph(js_graph)

def request_validator(topology_graph, request_graph):
    # Reading networkx file
    G_topology = read_json_file(topology_graph)
    G_request = read_json_file(request_graph)

    PMs = list(G_topology.nodes)
    set_state_or_nf = list(G_request.nodes)
    set_state, set_nf, set_replica = [], [], []
    for i in set_state_or_nf:
        if "function" in i:
            set_nf.append(i)
        elif "state" in i:
            set_state.append(i)
        elif "replica" in i:
            set_replica.append(i)
    print("Validating nodes in the request graph...")
    print("\tNode names")
    for i in list(G_request.nodes):
        if not ("function" in i or "state" in i or "replica" in i):
            raise RuntimeError("Given request graph is invalid! Invalid node: {}".format(i))

    print("Generating state-function adjacency matrix...")
    e_r = generating_req_adj(set_state, set_nf + set_replica, G_request)
    print("Generating delay matrix...")
    d = generating_delay_matrix(G_topology)

    print("Validating links in the request graph...")
    for u in set_state + set_nf + set_replica:
        for v in set_state + set_nf + set_replica:
            if "function" in u and "replica" in v:
                try:
                    G_request[u][v]
                    raise RuntimeError("Wrong Request Graph")
                except KeyError as e:
                    pass
            elif "function" in u and "function" in v:
                try:
                    G_request[u][v]
                    raise RuntimeError("Wrong Request Graph")
                except KeyError as e:
                    pass
            elif "state" in u and "replica" in v:
                #TODO
                pass
            elif "state" in u and "state" in v:
                try:
                    G_request[u][v]
                    raise RuntimeError("Wrong Request Graph")
                except KeyError as e:
                    pass

            elif "replica" in u and "function" in v:
                #TODO
                pass
            elif "replica" in u and "state" in v:
                try:
                    G_request[u][v]
                    raise RuntimeError("Wrong Request Graph")
                except KeyError as e:
                    pass
            elif "replica" in u and "replica" in v:
                try:
                    G_request[u][v]
                    raise RuntimeError("Wrong Request Graph")
                except KeyError as e:
                    pass


if __name__ == "__main__":

    from_num = 0
    TEST_NUM = 10
    exporting = True
    PROBLEM = 5
    mode = "fattree"  # test or fattree

    if not os.path.exists("optimization_results"):
        os.makedirs("optimization_results")

    if not os.path.exists("cplex_models/"):
        os.makedirs("cplex_models/")

    if not os.path.exists("graph_models/"):
        os.makedirs("graph_models/")

    f = open('optimization_results/summary.csv', mode='a')
    f_writer = csv.writer(f, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    f_writer.writerow(["----- {} -----".format(datetime.datetime.now())])
    f_writer.writerow(["Scenario", "OPTIMAL", "GREEDY", "FLOODING", "GREEDY %", "FLOODING %", "GREEDY RUNNING TIME",
                       "FLOODING RUNNING TIME"])
    f.close()

    for i in range(from_num, TEST_NUM):

        if mode == "test":
            create_test_topology(i, exporting, PROBLEM)

        if mode == "fattree":
            subprocess.call("./tree_topology_generator.py -s 1 -r 4 -f 4 -o {} -p {}".format(i, "p{}".format(PROBLEM)),
                            shell=True)

        request_validator("graph_models/p5_topology_graph_{}.json".format(i), "graph_models/p5_request_graph_{}.json".format(i))

        print(
            "PROBLEM {}---------------------------------------------------------------------------------------------").format(
            i)

        ### Getting Optimal solution #######################################################################################
        print("\nOPTIMAL SOLUTION:")
        if PROBLEM == 3:
            opt = p3_optimal_solver.solving_placement_problem_from_file(
                "graph_models/p3_topology_graph_{}.json".format(i),
                "graph_models/p3_request_graph_{}.json".format(i), i)
        elif PROBLEM == 5:
            opt = p5_optimal_solver.solving_placement_problem_from_file(
                "graph_models/p5_topology_graph_{}.json".format(i),
                "graph_models/p5_request_graph_{}.json".format(i),
                i)
        else:
            raise Exception("Invalid problem ID!")
        print(datetime.datetime.now())

        ### Getting Greedy solution ########################################################################################
        print("\nGREEDY SOLUTION:")
        greedy_t0 = datetime.datetime.now()
        print(greedy_t0)
        if PROBLEM == 3:
            greedy = p3_greedy_solver.solving_placement_problem_from_file(
                "graph_models/p3_topology_graph_{}.json".format(i),
                "graph_models/p3_request_graph_{}.json".format(i), i)
        elif PROBLEM == 5:
            greedy = p5_greedy_solver.solving_placement_problem_from_file(
                "graph_models/p5_topology_graph_{}.json".format(i),
                "graph_models/p5_request_graph_{}.json".format(i), i)

        greedy_t1 = datetime.datetime.now()
        greedy_rt = greedy_t1 - greedy_t0
        print("Running time: {}".format(greedy_rt))

        ### Getting some heuristic solution ################################################################################
        # print("\nTHIRD SOLUTION:")
        # flooding_t0 = datetime.datetime.now()
        # if PROBLEM == 3:
        #     flooding = p3_heuristic_solver.solving_placement_problem_from_file(
        #         "graph_models/topology_graph_{}.json".format(i),
        #         "graph_models/request_graph_{}.json".format(i), i)
        # flooding_t1 = datetime.datetime.now()
        # flooding_rt = flooding_t1 - flooding_t0
        # print("Running time: {}".format(flooding_rt))

        opt = float(opt)
        greedy = float(greedy)
        #flooding = float(flooding)
        flooding = 0
        flooding_rt = 0

        f = open('optimization_results/summary.csv', mode='a')
        f_writer = csv.writer(f, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        try:
            f_writer.writerow(["Scenario {}".format(i), opt, greedy, flooding, ((greedy / opt) * 100) - 100,
                               ((flooding / opt) * 100) - 100, greedy_rt, flooding_rt])
        except:
            f_writer.writerow(["Scenario {}".format(i), "-", "-", "-", "-", "-", greedy_rt, flooding_rt])
        f.close()

        print("-------------------------------------------------------------------------------------------------------")
