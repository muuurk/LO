#!/usr/bin/python
# ---------------------------------------------------------------------------
# File: p3_heuristic_solver.py
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

def get_PM_of_NF(graph, nf):
    for pm in list(graph.nodes):
        if nf in graph.nodes[pm]['NFs']:
            return pm
    raise Exception("Given NF is not mapped into any of the PMs")

def get_optimal_for_state(PMs, state_or_nf, G_request, G_topology, state_name, tmp_mapping):

    min_host = {"host": "", "cost": 100000000}
    nf_hosts = [pm for pm in PMs for nf in list(G_request.adj[state_name]) if nf in PMs[pm]['NFs']]

    best_nodes = []
    for pm in PMs:

        delay_cost = 0
        for dest_host in nf_hosts:
            path_length, path_nodes, negative_cycle = bf.bellman_ford(G_topology, source=pm, target=dest_host,
                                                                      weight="delay")
            delay_cost += path_length
        if delay_cost < min_host["cost"]:
            min_host["host"] = pm
            min_host["cost"] = delay_cost
            best_nodes = [pm]
        elif delay_cost == min_host["cost"]:
            best_nodes.append(pm)

    if len(best_nodes) > 1:
        capacity, load, states = get_tmp_mapping_data(best_nodes[0], tmp_mapping)
        best_load = capacity - load
        for i in best_nodes:
            c, l, s = get_tmp_mapping_data(i, tmp_mapping)
            cur_load = c - l
            if cur_load > best_load:
                min_host["host"] = i

    return min_host["host"], min_host["cost"]

def ordering_states(graph):
    states = []
    set_state, set_nf = bipartite.sets(graph)

    for i in set_state:
        no_insert = True
        for j in states:
            if len(graph.adj[i]) < len(graph.adj[j]):
                states.insert(states.index(j),str(i))
                no_insert = False
                break
            elif len(graph.adj[i]) == len(graph.adj[j]) and graph.nodes[i]['size'] < graph.nodes[j]['size']:
                states.insert(states.index(j),str(i))
                no_insert = False
                break
        if no_insert:
            states.append(str(i))
    return states

def solving_placement_problem_from_file(topology_graph, request_graph):
    # Reading networkx file
    G_topology = read_json_file(topology_graph)
    G_request = read_json_file(request_graph)

    solving_placement_problem(G_topology, G_request)

def init_tmp_mapping(PMs):
    tmp_mapping = []
    for i in PMs:
        if tmp_mapping == []:
            tmp_mapping.append({"node": i, "states": [], "load": 0, "capacity": PMs[i]["capacity"]})
            insterting = True
        else:
            insterting = False
            for j in tmp_mapping:
                if PMs[i]['capacity'] < j['capacity']:
                    tmp_mapping.insert(tmp_mapping.index(j), {"node": i, "states": [], "load": 0, "capacity": PMs[i]["capacity"]})
                    insterting = True
                    break
        if not insterting:
            tmp_mapping.append({"node": i, "states": [], "load": 0, "capacity": PMs[i]["capacity"]})
    return tmp_mapping

def mapping_state_to_node_in_tmp_mapping(state, node, tmp_mapping, state_or_nf, capacity = 0):

    states = []
    load = 0
    for i in tmp_mapping:
        if i["node"] == node:
            states = i["states"]
            load = i['load']
            capacity = i['capacity']
            del tmp_mapping[tmp_mapping.index(i)]
            break

    insterting = False
    for j in tmp_mapping:
        if (capacity - (load + state_or_nf[state]['size'])) < (j['capacity'] - j['load']):
            states.append(state)
            tmp_mapping.insert(tmp_mapping.index(j), {"node": node, "states": states, "load": load + state_or_nf[state]['size'], "capacity": capacity})
            insterting = True
            break
    if not insterting:
        states.append(state)
        tmp_mapping.append({"node": node, "states": states, "load": load + state_or_nf[state]['size'], "capacity": capacity})

    return tmp_mapping

def adding_new_node_to_tmp_mapping(node, tmp_mapping, capacity):
    insterting = False
    for j in tmp_mapping:
        if capacity < (j['capacity'] - j['load']):
            tmp_mapping.insert(tmp_mapping.index(j),
                               {"node": node, "states": [], "load": 0, "capacity": capacity})
            insterting = True
            break
    if not insterting:
        tmp_mapping.append(
            {"node": node, "states": [], "load": 0, "capacity": capacity})
    return tmp_mapping

def deleting_state_from_tmp_mapping(state, state_or_nf, node, tmp_mapping):

    states = []
    load = 0
    capacity = 0
    for i in tmp_mapping:
        if i["node"] == node:
            i["states"].pop(i["states"].index(state))
            states = i["states"]
            capacity = i['capacity']
            del tmp_mapping[tmp_mapping.index(i)]
            break

    for state in states:
        tmp_mapping = mapping_state_to_node_in_tmp_mapping(state,node,tmp_mapping,state_or_nf, capacity)

    if states == []:
        tmp_mapping = adding_new_node_to_tmp_mapping(node, tmp_mapping, capacity)

    return tmp_mapping

def get_tmp_mapping_data(node, tmp_mapping):
    for i in tmp_mapping:
        if i["node"] == node:
            return i["capacity"], i["load"], i["states"]

def exist_minus_capacity(tmp_mapping):
    for i in tmp_mapping:
        if (i['capacity']-i['load']) < 0:
            return True
    return False

def get_state_to_move(tmp_mapping, state_or_nf):
    states = tmp_mapping[0]["states"]
    smallest_state = states[0]
    for s in states:
        if state_or_nf[s]['size'] < state_or_nf[smallest_state]['size']:
            smallest_state = s
    return smallest_state

def get_possible_dest_nodes(tmp_mapping, no_dst, state, state_size):
    dest_hosts = []
    for i in tmp_mapping:
        if i['node'] != no_dst:
            inserting = False
            if i['capacity'] - i['load'] >= state_size:
                if dest_hosts == []:
                    dest_hosts.append(i)
                else:
                    for j in dest_hosts:
                        if i['capacity'] - (i['load'] + state_size) < j['capacity'] - (j['load'] + state_size):
                            dest_hosts.insert(dest_hosts.index(i),j)
                            inserting = True
                            break
                    if not inserting:
                        dest_hosts.append(i)

    return dest_hosts

def get_cost_of_mapping(state, src_host, PMs, G_request, G_topology):
    dst_hosts = [pm for pm in PMs for nf in list(G_request.adj[state]) if nf in PMs[pm]['NFs']]
    delay_cost = 0
    for dest_host in dst_hosts:
        path_length, path_nodes, negative_cycle = bf.bellman_ford(G_topology, source=src_host, target=dest_host,
                                                                  weight="delay")
        delay_cost += path_length
    return delay_cost

def solving_placement_problem(G_topology, G_request):

    PMs = G_topology.nodes
    state_or_nf = G_request.nodes

    ordered_states = ordering_states(G_request)
    tmp_mapping = init_tmp_mapping(PMs)

    for s in ordered_states:
        node, cost = get_optimal_for_state(PMs, state_or_nf, G_request, G_topology, s, tmp_mapping)
        tmp_mapping = mapping_state_to_node_in_tmp_mapping(s, node, tmp_mapping, state_or_nf)


    while exist_minus_capacity(tmp_mapping):

        state_to_move = get_state_to_move(tmp_mapping,state_or_nf)
        src_host=tmp_mapping[0]['node']
        dst_hosts = get_possible_dest_nodes(tmp_mapping, src_host, state_to_move, state_or_nf[state_to_move]['size'])
        if dst_hosts == []:
            raise Exception("There is no valid mapping!")

        tmp_mapping = deleting_state_from_tmp_mapping(state_to_move, state_or_nf, src_host, tmp_mapping)
        tmp_mapping = mapping_state_to_node_in_tmp_mapping(state_to_move,dst_hosts[0]['node'],tmp_mapping,state_or_nf)

    mapping = tmp_mapping
    sum_cost = 0
    for m in mapping:
        for s in m['states']:
            cost = get_cost_of_mapping(s, m["node"], PMs, G_request, G_topology)
            sum_cost += cost
            print("State {} -> PM {}, COST: {}".format(s, m["node"], cost))

    print("SUMMA COST: {}".format(sum_cost))


