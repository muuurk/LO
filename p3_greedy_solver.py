#!/usr/bin/python
# ---------------------------------------------------------------------------
# File: p3_greedy_solver.py
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

def read_json_file(filename):
    with open(filename) as f:
        js_graph = json.load(f)
    return json_graph.node_link_graph(js_graph)

def ordering_states(graph, set_state, set_nf):
    states = []

    for i in set_state:
        no_insert = True
        for j in states:
            if len(graph.adj[i]) > len(graph.adj[j]):
                states.insert(states.index(j),str(i))
                no_insert = False
                break
            elif len(graph.adj[i]) == len(graph.adj[j]) and graph.nodes[i]['size'] > graph.nodes[j]['size']:
                states.insert(states.index(j), str(i))
                no_insert = False
                break
        if no_insert:
            states.append(str(i))
    return states

def get_PM_of_NF(graph, nf):
    for pm in list(graph.nodes):
        if nf in graph.nodes[pm]['NFs']:
            return pm
    raise Exception("Given NF is not mapped into any of the PMs")

def try_to_map_locally(G_request, G_topology, mapping, s):
    if len(G_request.adj[s]) == 1:
        nf = [n for n in G_request.neighbors(s)][0]
        pm = get_PM_of_NF(G_topology, nf)
        if G_topology.nodes[pm]['capacity'] >= G_request.nodes[s]['size']:
            mapping[s] = {"host":pm, "cost":0}
            G_topology.nodes[mapping[s]["host"]]['capacity'] = G_topology.nodes[mapping[s]["host"]]['capacity'] - G_request.nodes[s]['size']
            return True, mapping
    return False, mapping

def solving_placement_problem_from_file(topology_graph, request_graph, test_num):
    # Reading networkx file
    G_topology = read_json_file(topology_graph)
    G_request = read_json_file(request_graph)

    PMs = G_topology.nodes
    state_or_nf = G_request.nodes

    set_state_or_nf = list(G_request.nodes)
    set_state, set_nf = [], []
    for i in set_state_or_nf:
        if "function" in i:
            set_nf.append(i)
        elif "state" in i:
            set_state.append(i)

    ordered_states = ordering_states(G_request,set_state, set_nf )

    mapping = {i : {} for i in ordered_states}
    valid_mapping = True

    for s in ordered_states:

        if s == "state_4":
            asd = 0

        success_map, mapping = try_to_map_locally(G_request, G_topology, mapping, s)
        if not success_map:

            min_host = {"host":"", "cost":100000000}
            nf_hosts = [pm for pm in PMs for nf in list(G_request.adj[s]) if nf in PMs[pm]['NFs']]
            for pm in PMs:
                if PMs[pm]['capacity'] >= state_or_nf[s]['size']:

                    delay_cost = 0
                    for dest_host in nf_hosts:
                        path_length, path_nodes, negative_cycle = bf.bellman_ford(G_topology, source=pm, target=dest_host, weight="delay")
                        delay_cost += path_length
                    if delay_cost < min_host["cost"]:
                        min_host["host"] = pm
                        min_host["cost"] = delay_cost

            if min_host["host"] != "":
                mapping[s] = {"host":  min_host["host"], "cost":  min_host["cost"]}
                PMs[min_host["host"]]['capacity'] = PMs[min_host["host"]]['capacity'] - state_or_nf[s]['size']
            else:
                valid_mapping = False
                print("There is no valid mapping for the given problem by the Greedy Algorythm")


    f = open("optimization_results/p3_greedy_result_{}.json".format(test_num), "a")
    if valid_mapping:
        sum_cost = 0
        for state, map in mapping.iteritems():
            sum_cost += map["cost"]
            print("State {} -> PM {}, COST: {}".format(state, map["host"], map["cost"]))
            f.write("State {} -> PM {}, COST: {}\n".format(state, map["host"], map["cost"]))

        print("*** Delay cost: {} ***".format(sum_cost))
        f.write("*** Delay cost: {} ***\n".format(sum_cost))
        return sum_cost
    else:
        f.write("There is no valid mapping for the given problem by the Greedy Algorythm\n")
        return 0



