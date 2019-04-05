#!/usr/bin/python
# ---------------------------------------------------------------------------
# File: p5_greedy_solver.py
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
import itertools
import datetime
import os

def read_json_file(filename):
    with open(filename) as f:
        js_graph = json.load(f)
    return json_graph.node_link_graph(js_graph)


def get_size_with_replicas(state, state_name):
    if "state" in state_name:
        return (len(state["replicas"]) + 1) * state["size"]
    else:
        return state["size"]

def ordering_states(graph, set_state):
    states = []
    for i in set_state:
        no_insert = True
        for j in states:
            """
            if len(graph.adj[i]) > len(graph.adj[j]):
                states.insert(states.index(j), str(i))
                no_insert = False
                break
            """
            if get_size_with_replicas(graph.nodes[i], i) > get_size_with_replicas(graph.nodes[j], j):
                states.insert(states.index(j), str(i))
                no_insert = False
                break
        if no_insert:
            states.append(str(i))
    return states


def get_PM_of_NF(graph, ve, mapping):
    if ve == "":
        return None
    if "function" in ve:
        for pm in list(graph.nodes):
            if ve in graph.nodes[pm]['NFs']:
                return pm
    else:
        if mapping[ve]["host"] != "":
            return mapping[ve]["host"]
    raise Exception("Given NF is not mapped into any of the PMs")

def get_function_neighbors(u, graph, set_function):
    functions = [i for i in graph.neighbors(u) if "function" in i]
    for v in set_function:
        if u in list(graph.neighbors(v)):
            if v not in functions:
                functions.append(v)
    return functions

def get_replica_neighbors(u, graph):
    replicas = [i for i in graph.neighbors(u) if "replica" in i]
    return replicas

def get_state_neighbors(u, graph, set_state):
    states = [i for i in graph.neighbors(u) if "state" in i]
    for v in set_state:
        if u in list(graph.neighbors(v)):
            if v not in states:
                states.append(v)
    return states

def try_to_map_locally(G_request, G_topology, mapping, s):
    if "state" in s:
        if len(get_function_neighbors(s,G_request)) == 1:
            nf = get_function_neighbors(s,G_request)[0]
            pm = get_PM_of_NF(G_topology, nf)
            if G_topology.nodes[pm]['capacity'] >= G_request.nodes[s]['size']:
                mapping[s] = {"host": pm, "cost": 0}
                G_topology.nodes[mapping[s]["host"]]['capacity'] = G_topology.nodes[mapping[s]["host"]]['capacity'] - \
                                                                   G_request.nodes[s]['size']
                return True, mapping
    return False, mapping

def get_aa_nodes(state, G_request, mapping, master_state = None):

    nodes = []

    if "replica" in state:
        try:
            nodes.append(mapping[master_state]["host"])
        except:
            pass
        replica_mates = G_request.nodes[master_state]["replicas"]
        for r in replica_mates:
            if r != state:
                try:
                    if mapping[r]["host"] not in nodes:
                        nodes.append(mapping[r]["host"])
                except:
                    pass

    elif "state" in state:
        for r in G_request.nodes[state]["replicas"]:
            try:
                nodes.append(mapping[r]["host"])
            except:
                pass
    elif "function" in state:
        return []
    else:
        raise Exception("Invalid state {}".format(state))
    return nodes


def do_mapping(G_request, G_topology, PMs, mapping, virtual_element, pairing = {}, writer_count = 0, master = ""):

    #FIXME: cost should be infinity
    min_host = {"host": "", "cost": 100000000}
    max_host = {"host": "", "cost": 0}
    destinations = [pairing[virtual_element]]
    if writer_count > 0 and master != "":
        destinations.append(master)

    # In case of replicas
    max_hosts = []
    aa_nodes = get_aa_nodes(virtual_element, G_request, mapping, master)

    tmp_dst_hosts = [get_PM_of_NF(G_topology, i, mapping) for i in destinations]
    # delete none hosts
    dst_hosts = [tmp_dst_hosts[i] for i in range(len(tmp_dst_hosts)) if tmp_dst_hosts[i] != None]
    for pm in PMs:
        if pm not in aa_nodes:
            if PMs[pm]['capacity'] >= G_request.nodes[virtual_element]['size']:
                if dst_hosts != []:
                    delay_cost = 0
                    for dest_host in dst_hosts:
                        path_length, path_nodes, negative_cycle = bf.bellman_ford(G_topology, source=pm,
                                                                                  target=dest_host, weight="delay")
                        delay_cost += path_length
                    if delay_cost < min_host["cost"]:
                        min_host["host"] = pm
                        min_host["cost"] = delay_cost
                else:
                    if max_hosts == []:
                        max_hosts.append({"host":pm, "capacity":PMs[pm]["capacity"]})
                    else:
                        inserting = False
                        for i in max_hosts:
                            if i["capacity"] < PMs[pm]['capacity']:
                                max_hosts.insert(max_hosts.index(i),{'host':pm,'capacity':PMs[pm]['capacity']})
                                inserting = True
                                break
                        if not inserting:
                            max_hosts.append({'host': pm, 'capacity': PMs[pm]['capacity']})
    if max_hosts != []:
        mapping[virtual_element] = {"host": max_hosts[0]["host"]}
        PMs[max_hosts[0]["host"]]['capacity'] = PMs[max_hosts[0]["host"]]['capacity'] - G_request.nodes[virtual_element]['size']

    elif min_host["host"] != "":
        mapping[virtual_element] = {"host": min_host["host"], "cost": min_host["cost"]}
        PMs[min_host["host"]]['capacity'] = PMs[min_host["host"]]['capacity'] - G_request.nodes[virtual_element]['size']

    else:
        valid_mapping = False
        print("There is no valid mapping for the given problem by the Greedy Algorythm")


def map_with_no_replicas(G_request, G_topology, mapping, PMs, states, replicas, nfs, actual_state):
    success_map, mapping = try_to_map_locally(G_request, G_topology, mapping, actual_state)
    if not success_map:

        min_host = {"host": "", "cost": 100000000}
        nf_hosts = [pm for pm in PMs for nf in list(G_request.adj[s]) if nf in PMs[pm]['NFs']]
        for pm in PMs:
            if PMs[pm]['capacity'] >= states[actual_state]['size']:

                delay_cost = 0
                for dest_host in nf_hosts:
                    path_length, path_nodes, negative_cycle = bf.bellman_ford(G_topology, source=pm, target=dest_host,
                                                                              weight="delay")
                    delay_cost += path_length
                if delay_cost < min_host["cost"]:
                    min_host["host"] = pm
                    min_host["cost"] = delay_cost

        if min_host["host"] != "":
            mapping[s] = {"host": min_host["host"], "cost": min_host["cost"]}
            PMs[min_host["host"]]['capacity'] = PMs[min_host["host"]]['capacity'] - states[actual_state]['size']
        else:
            valid_mapping = False
            print("There is no valid mapping for the given problem by the Greedy Algorythm")


def get_writing_edge_count(ve, G_request, set_nf):
    num_writing_edges = 0
    edges = []
    neigbors = get_function_neighbors(ve,G_request, set_nf)
    for n in neigbors:
        try:
            G_request[n][ve]
            num_writing_edges += 1
            edges.append((n,ve))
        except:
            pass
    return num_writing_edges, edges


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


def generating_delay_matrix(graph):
    d = {(i, j): 1000000 for i in list(graph.nodes) for j in list(graph.nodes)}
    for i in list(graph.nodes):
        for j in list(graph.nodes):
            path_length, path_nodes, negative_cycle = bf.bellman_ford(graph, source=i, target=j, weight="delay")
            d[(i, j)] = path_length
    return d

def solving_placement_problem_from_file(topology_graph, request_graph, test_num, results_path):

    if not os.path.isfile("{}/p5_greedy_result_{}.json".format(results_path, test_num)):

        # Reading networkx file
        G_topology = read_json_file(topology_graph)
        G_request = read_json_file(request_graph)

        PMs = G_topology.nodes

        set_virtual_nodes = list(G_request.nodes)
        set_state, set_replica, set_nf = [], [], []
        for i in set_virtual_nodes:
            if "function" in i:
                set_nf.append(i)
            elif "state" in i:
                set_state.append(i)
            elif "replica" in i:
                set_replica.append(i)
            else:
                raise Exception("Invalid request graph")

        t1 = datetime.datetime.now()
        ordered_states = ordering_states(G_request, set_state)

        mapping = {i: {} for i in ordered_states + set_replica}
        valid_mapping = True

        for s in ordered_states:

            if get_replica_neighbors(s, G_request) == 0:
                map_with_no_replicas(G_request, G_topology, mapping, PMs, set_state, set_replica, set_nf, s)
            else:
                replicas = get_replica_neighbors(s, G_request)
                functions = get_function_neighbors(s, G_request, set_nf)
                we_count, writing_edges = get_writing_edge_count(s, G_request, set_nf)
                if we_count > 1:
                    ve_function_pairing = {replicas[i]:"" for i in range(len(replicas))}
                    for j in range(len(functions)):
                        ve_function_pairing[replicas[j]] = functions[j]
                else:
                    ve_function_pairing = {i: "" for i in [s] + replicas}
                    unpaired_functions = functions
                    if we_count == 1:
                        writer_function =writing_edges[0][0]
                        ve_function_pairing[s] = writer_function
                        unpaired_functions.remove(writer_function)
                    else:
                        ve_function_pairing[s] = functions[0]
                        unpaired_functions.remove(functions[0])

                    iter = 0
                    for ve, function in ve_function_pairing.items():
                        try:
                            if ve_function_pairing[ve] == "":
                                ve_function_pairing[ve] = unpaired_functions[iter]
                                iter += 1
                        except:
                            break

                do_mapping(G_request, G_topology, PMs, mapping, s, ve_function_pairing, we_count)

                for r in replicas:
                    do_mapping(G_request, G_topology, PMs, mapping, r, ve_function_pairing, we_count, s)

        t2 = datetime.datetime.now()
        f = open("optimization_results/p5_greedy_result_{}.json".format(test_num), "a")
        if valid_mapping:
            for state, map in mapping.items():
                #sum_cost += map["cost"]
                f.write("State {} -> PM {}, COST: ?\n".format(state, map["host"]))
                print("x_({},{}) = 1".format(map["host"], state))

            # Calculating cost
            servers = [i for i in PMs if "server" in i]
            server_permutations = list(itertools.permutations(servers, 2))

            x_vars = {(i, u): 0 for i in PMs for u in set_state + set_replica + set_nf}

            for state, map in mapping.items():
                x_vars[map["host"], state] = 1

            for i in PMs:
                if PMs[i]['NFs'] != []:
                    for u in PMs[i]['NFs']:
                        x_vars[i, u] = 1

            print("Generating state-function adjacency matrix...")
            e_r = generating_req_adj(set_state, set_nf + set_replica, G_request)
            print("Generating delay matrix...")
            d = generating_delay_matrix(G_topology)

            index_permutations = list(itertools.permutations((set_state + set_nf + set_replica), 2))
            z_vars = {(u, v): 0 for u, v in index_permutations}

            for u,v in index_permutations:
                if "function" in u and "state" in v:
                    if e_r[u,v] == 1:
                        z_vars[u,v] = 1
                elif "function" in u and "replica" in v:
                    if e_r[u,v] == 1:
                        raise Exception("Wrong Request Graph")
                elif "function" in u and "function" in v:
                    if e_r[u, v] == 1:
                        raise Exception("Wrong Request Graph")
                elif "state" in u and "function" in v:
                    if e_r[u, v] == 1:
                        replicas = get_replica_neighbors(u, G_request)
                        if len(replicas) == 0:
                            z_vars[u,v] = 1
                        else:
                            links = [(u,v)] + [(r,v) for r in replicas]
                            # FIXME: infinity
                            min_cost = 10000000000
                            min_link = None
                            for i,j in links:
                                source = get_PM_of_NF(G_topology, i, mapping)
                                destination = get_PM_of_NF(G_topology, j, mapping)
                                path_length, path_nodes, negative_cycle = bf.bellman_ford(G_topology, source=source,
                                                                                      target=destination,
                                                                                      weight="delay")
                                if path_length < min_cost:
                                    min_cost = path_length
                                    min_link = (i,j)
                            if min_link == (u,v):
                                z_vars[u,v] = 1
                elif "state" in u and "replica" in v:
                    if e_r[u, v] == 1:
                        z_vars[u,v] = 1
                elif "state" in u and "state" in v:
                    if e_r[u, v] == 1:
                        raise Exception("Wrong Request Graph")
                elif "replica" in u and "function" in v:
                    if e_r[u, v] == 1:
                        master = next(i for i in set_state if u in G_request.nodes[i]['replicas'])
                        replicas = get_replica_neighbors(master, G_request)
                        links = [(r, v) for r in replicas] + [(master,v)]
                        # FIXME: infinity
                        min_cost = 10000000000
                        min_link = None
                        for i, j in links:
                            source = get_PM_of_NF(G_topology, i, mapping)
                            destination = get_PM_of_NF(G_topology, j, mapping)
                            path_length, path_nodes, negative_cycle = bf.bellman_ford(G_topology, source=source,
                                                                                      target=destination,
                                                                                      weight="delay")
                            if path_length < min_cost:
                                min_cost = path_length
                                min_link = (i, j)
                        if min_link == (u, v):
                            z_vars[u, v] = 1
                elif "replica" in u and "state" in v:
                    if e_r[u, v] == 1:
                        raise Exception("Wrong Request Graph")
                elif "replica" in u and "replica" in v:
                    if e_r[u, v] == 1:
                        raise Exception("Wrong Request Graph")

            sum_cost = 0

            print("x_vars[i, u] * \tx_vars[j, v] * \te_r[u, v] * \td[i, j] * \tz_vars[u, v]")
            for i, j in server_permutations:
                for u, v in list(itertools.permutations(set_state + set_replica + set_nf, 2)):
                    c = x_vars[i, u] * x_vars[j, v] * e_r[u, v] * d[i, j] * z_vars[u, v]
                    if c > 0:
                        pass
                        #print("i : {}\tj : {}\tu : {}\tv : {}".format(i,j,u,v))
                        #print("{} * {} * {} * {} * {}".format(x_vars[i, u], x_vars[j, v], e_r[u, v], d[i, j], z_vars[u, v]))
                        #print("----------------------------------------------------")
                    sum_cost += c

            print("*** RUNNING TIME: {} ***".format(t2-t1))
            f.write("*** RUNNING TIME: {} ***\n".format(t2-t1))

            print("*** Delay cost: {} ***".format(sum_cost))
            f.write("*** Delay cost: {} ***\n".format(sum_cost))

            return sum_cost, t2-t1
        else:
            f.write("There is no valid mapping for the given problem by the Greedy Algorythm\n")
            return 0, t2-t1
    else:
        with open("{}/p5_greedy_result_{}.json".format(results_path, test_num)) as f:
            lines = f.read().splitlines()
            cost = int(lines[-1].split(" ")[3])
            rt = lines[-2].split(" ")[3]
            print("*** RUNNING TIME: {} ***".format(rt))
            print("*** Delay cost: {} ***".format(cost))
            return cost, rt



