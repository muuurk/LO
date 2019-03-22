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

import p3_greedy_solver
import p3_optimal_solver
import p3_heuristic_solver
import matplotlib.pyplot as plt
import subprocess
import csv
import os


def merge_two_dicts(x, y):
    z = x.copy()   # start with x's keys and values
    z.update(y)    # modifies z with y's keys and values & returns None
    return z

def generating_delay_matrix(graph):
    d = {}
    for i in list(graph.nodes):
        for j in list(graph.nodes):
            path_length, path_nodes, negative_cycle = bf.bellman_ford(graph, source=i, target=j, weight="delay")
            d = merge_two_dicts(d, { (i,j) : path_length})
    return d

def generating_req_adj(nfs, states, graph):
    adj = {}
    for i in list(states):
        for j in list(nfs):
            try:
                graph[j][i]
                adj = merge_two_dicts(adj, { (j,i) : 1})
            except:
                adj = merge_two_dicts(adj, {(j, i): 0})
    return adj

def generating_nf_mapping_matrix(graph):
    m = {}
    for i in list(graph.nodes):
        for j in graph.nodes[i]['NFs']:
            m = merge_two_dicts(m, {j: i})
    return m

def create_test_topology(test_num, exporting):
    ### Generating topology graph ############################

    G_topology = nx.Graph()

    # Vertices
    """
    G_topology.add_node("PM1", capacity=2, NFs=["nf1"])
    G_topology.add_node("PM2", capacity=3, NFs=[])
    G_topology.add_node("PM3", capacity=4, NFs=[])
    G_topology.add_node("PM4", capacity=1, NFs=["nf2"])
    """
    G_topology.add_node("PM1", capacity=random.randint(1, 5), NFs=["function_1"])
    G_topology.add_node("PM2", capacity=random.randint(1, 5), NFs=[])
    G_topology.add_node("PM3", capacity=random.randint(1, 5), NFs=[])
    G_topology.add_node("PM4", capacity=random.randint(1, 5), NFs=["function_2"])

    # Edges
    """
    G_topology.add_edges_from([('PM1', 'PM2', {'delay': 2}),
                               ('PM1', 'PM3', {'delay': 3}),
                               ('PM2', 'PM3', {'delay': 4}),
                               ('PM2', 'PM4', {'delay': 5}),
                               ('PM3', 'PM4', {'delay': 6)])
    """
    G_topology.add_edges_from([('PM1', 'PM2', {'delay': random.randint(1, 5)}),
                               ('PM1', 'PM3', {'delay': random.randint(1, 5)}),
                               ('PM2', 'PM3', {'delay': random.randint(1, 5)}),
                               ('PM2', 'PM4', {'delay': random.randint(1, 5)}),
                               ('PM3', 'PM4', {'delay': random.randint(1, 5)})])

    # Exporting
    if exporting:
        topology_json = json_graph.node_link_data(G_topology)
        with open('graph_models/topology_graph_{}.json'.format(test_num), 'w') as outfile:
            json.dump(topology_json, outfile)

    ### Generating request graph ############################

    G_request = nx.Graph()

    # Vertices
    """
    G_request.add_nodes_from([('s1', {'size': 1}),
                              ('s2', {'size': 2}),
                              ('s3', {'size': 2}),
                              ('s4', {'size': 1})],
                             bipartite=0)
    """
    G_request.add_nodes_from([('state_1', {'size': random.randint(1, 3)}),
                              ('state_2', {'size': random.randint(1, 3)}),
                              ('state_3', {'size': random.randint(1, 3)}),
                              ('state_4', {'size': random.randint(1, 3)})],
                             bipartite=0)
    G_request.add_nodes_from(['function_1', 'function_2'], bipartite=1)

    # Edges
    G_request.add_edges_from([('state_1', 'function_1'), ('state_2', 'function_1'), ('state_3', 'function_1'), ('state_3', 'function_2'), ('state_4', 'function_2')])

    # Exporting
    if exporting:
        request_json = json_graph.node_link_data(G_request)
        with open('graph_models/request_graph_{}.json'.format(test_num), 'w') as outfile:
            json.dump(request_json, outfile)

    G_topology.number_of_nodes()
    G_topology.number_of_edges()
    list(G_topology.nodes)
    list(G_topology.edges)

    """
    nx.draw(G_topology, with_labels=True)
    plt.show()

    nx.draw(G_request, with_labels=True)
    plt.show()
    """""


if __name__ == "__main__":

    from_num = 10
    TEST_NUM = 15
    exporting = False
    mode="fattree" #test or fattree

    if not os.path.exists("optimization_results"):
        os.makedirs("optimization_results")

    if not os.path.exists("cplex_models/"):
        os.makedirs("cplex_models/")

    if not os.path.exists("graph_models/"):
        os.makedirs("graph_models/")

    f = open('optimization_results/summary.csv', mode='a')
    f_writer = csv.writer(f, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    f_writer.writerow(["----- {} -----".format(datetime.datetime.now())])
    f_writer.writerow(["Scenario", "OPTIMAL", "GREEDY", "FLOODING", "GREEDY %", "FLOODING %"])
    f.close()

    for i in range(from_num, TEST_NUM):

        ### Converting input for cplex from networkx #############

        # # Set of Physical Machines
        # set_PM = list(G_topology.nodes)
        #
        # # Set of States and Network Functions
        # set_state, set_nf = bipartite.sets(G_request)
        #
        # # Set of State's sizes
        # s = {i: G_request.nodes[i]['size'] for i in set_state}
        #
        # # Set of PM's capacities
        # c = {i: G_topology.nodes[i]['capacity'] for i in set_PM}
        #
        # # Topology edges
        # e_t = {i: G_topology.edges[i]['delay'] for i in list(G_topology.edges)}
        #
        # # Delay matrix
        # d = generating_delay_matrix(G_topology)
        #
        # # Edge matrix of states and nfs
        # e_r = generating_req_adj(set_state, set_nf, G_request)
        #
        # # Mapping of NFs
        # M = generating_nf_mapping_matrix(G_topology)

        if mode == "test":
            if exporting:
                create_test_topology(i, exporting)

        if mode == "fattree":
            subprocess.call("./tree_topology_generator.py -s 10 -r 10 -o {}".format(i), shell=True)


        print("PROBLEM {}---------------------------------------------------------------------------------------------").format(i)

        ### Getting Optimal solution #######################################################################################
        print("\nOPTIMAL SOLUTION:")
        opt = p3_optimal_solver.solving_placement_problem_from_file("graph_models/topology_graph_{}.json".format(i),
                                                             "graph_models/request_graph_{}.json".format(i), i)
        print(datetime.datetime.now())

        ### Getting Greedy solution ########################################################################################
        print("\nGREEDY SOLUTION:")
        print(datetime.datetime.now())
        greedy = p3_greedy_solver.solving_placement_problem_from_file("graph_models/topology_graph_{}.json".format(i),
                                                             "graph_models/request_graph_{}.json".format(i), i)
        print(datetime.datetime.now())

        ### Getting some heuristic solution ################################################################################
        print("\nTHIRD SOLUTION:")
        print(datetime.datetime.now())
        flooding = p3_heuristic_solver.solving_placement_problem_from_file("graph_models/topology_graph_{}.json".format(i),
                                                             "graph_models/request_graph_{}.json".format(i), i)
        print(datetime.datetime.now())

        opt = float(opt)
        greedy = float(greedy)
        flooding = float(flooding)

        f = open('optimization_results/summary.csv', mode='a')
        f_writer = csv.writer(f, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        try:
            f_writer.writerow(["Scenario {}".format(i), opt, greedy, flooding, ((greedy/opt)*100)-100, ((flooding/opt)*100)-100])
        except:
            f_writer.writerow(["Scenario {}".format(i)])
        f.close()

        print("-------------------------------------------------------------------------------------------------------")