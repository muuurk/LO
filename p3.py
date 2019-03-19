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

import p3_greedy_solver
import p3_optimal_solver
import p3_heuristic_solver


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

if __name__ == "__main__":

    TEST_NUM = 15
    EXPORTING = False

    ### Generating topology graph ############################

    G_topology = nx.Graph()

    # Vertices
    """
    G_topology.add_node("PM1", capacity=2, NFs=["nf1"])
    G_topology.add_node("PM2", capacity=3, NFs=[])
    G_topology.add_node("PM3", capacity=4, NFs=[])
    G_topology.add_node("PM4", capacity=1, NFs=["nf2"])
    """
    G_topology.add_node("PM1", capacity=random.randint(1,5), NFs=["nf1"])
    G_topology.add_node("PM2", capacity=random.randint(1,5), NFs=[])
    G_topology.add_node("PM3", capacity=random.randint(1,5), NFs=[])
    G_topology.add_node("PM4", capacity=random.randint(1,5), NFs=["nf2"])

    # Edges
    """
    G_topology.add_edges_from([('PM1', 'PM2', {'delay': 2}),
                               ('PM1', 'PM3', {'delay': 3}),
                               ('PM2', 'PM3', {'delay': 4}),
                               ('PM2', 'PM4', {'delay': 5}),
                               ('PM3', 'PM4', {'delay': 6)])
    """
    G_topology.add_edges_from([('PM1', 'PM2', {'delay': random.randint(1,5)}),
                               ('PM1', 'PM3', {'delay': random.randint(1,5)}),
                               ('PM2', 'PM3', {'delay': random.randint(1,5)}),
                               ('PM2', 'PM4', {'delay': random.randint(1,5)}),
                               ('PM3', 'PM4', {'delay': random.randint(1,5)})])

    # Exporting
    if EXPORTING:
        topology_json = json_graph.node_link_data(G_topology)
        with open('topology_graph_{}.json'.format(TEST_NUM), 'w') as outfile:
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
    G_request.add_nodes_from([('s1', {'size': random.randint(1,3)}),
                              ('s2', {'size': random.randint(1,3)}),
                              ('s3', {'size': random.randint(1,3)}),
                              ('s4', {'size': random.randint(1,3)})],
                             bipartite=0)
    G_request.add_nodes_from(['nf1', 'nf2'], bipartite=1)

    # Edges
    G_request.add_edges_from([('s1', 'nf1'), ('s2', 'nf1'), ('s3', 'nf1'), ('s3', 'nf2'), ('s4', 'nf2')])

    # Exporting
    if EXPORTING:
        request_json = json_graph.node_link_data(G_request)
        with open('request_graph_{}.json'.format(TEST_NUM), 'w') as outfile:
            json.dump(request_json, outfile)

    G_topology.number_of_nodes()
    G_topology.number_of_edges()
    list(G_topology.nodes)
    list(G_topology.edges)

    ### Converting input for cplex from networkx #############

    # Set of Physical Machines
    set_PM = list(G_topology.nodes)

    # Set of States and Network Functions
    set_state, set_nf = bipartite.sets(G_request)

    # Set of State's sizes
    s = {i: G_request.nodes[i]['size'] for i in set_state}

    # Set of PM's capacities
    c = {i: G_topology.nodes[i]['capacity'] for i in set_PM}

    # Topology edges
    e_t = {i: G_topology.edges[i]['delay'] for i in list(G_topology.edges)}

    # Delay matrix
    d = generating_delay_matrix(G_topology)

    # Edge matrix of states and nfs
    e_r = generating_req_adj(set_state, set_nf, G_request)

    # Mapping of NFs
    M = generating_nf_mapping_matrix(G_topology)


    ### Getting Optimal solution #######################################################################################
    print("\nOPTIMAL SOLUTION:")
    #p3_optimal_solver.solving_placement_problem(set_PM, set_state, set_nf, s, c, d, e_r, M)
    p3_optimal_solver.solving_placement_problem_from_file("topology_graph_{}.json".format(TEST_NUM),
                                                         "request_graph_{}.json".format(TEST_NUM))

    ### Getting Greedy solution ########################################################################################
    print("\nGREEDY SOLUTION:")
    p3_greedy_solver.solving_placement_problem_from_file("topology_graph_{}.json".format(TEST_NUM), "request_graph_{}.json".format(TEST_NUM))

    ### Getting some heuristic solution ################################################################################
    print("\nTHIRD SOLUTION:")
    p3_heuristic_solver.solving_placement_problem_from_file("topology_graph_{}.json".format(TEST_NUM), "request_graph_{}.json".format(TEST_NUM))