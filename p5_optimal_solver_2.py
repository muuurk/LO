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
import subprocess
import xmltodict

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


def solving_placement_problem_from_file(topology_graph, request_graph, test_num, CPLEX_PATH, cplex_models_path,
                                        results_path, locally):
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

    if not os.path.isfile("{}/p5_cplex_model_{}_2.lp".format(cplex_models_path, test_num)):
        cplex_f = open('{}/p5_cplex_model_{}_2.lp'.format(cplex_models_path, test_num), mode='a')

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

        # ## Into File ############################################################################################

        cplex_f = open('{}/p5_cplex_model_{}_2.lp'.format(cplex_models_path, test_num), mode='a')
        cplex_f.write("Minimize\n obj: [ ")

        servers = [i for i in set_PM if "server" in i]
        server_permutations = list(itertools.permutations(servers, 2))
        first = True
        for i, j in server_permutations:
            asd = list(itertools.permutations(set_state + set_replica + set_nf, 2))
            for u, v in asd:
                if (e_r[u, v] * d[i, j] * 2 > 0):
                    if first:
                        cplex_f.write(
                            " {} y_({},{})_({},{})*z_({},{})\n".format(e_r[u, v] * d[i, j] * 2, i, u, j, v, u, v))
                        first = False
                    else:
                        cplex_f.write(
                            " + {} y_({},{})_({},{})*z_({},{})\n".format(e_r[u, v] * d[i, j] * 2, i, u, j, v, u, v))

        cplex_f.close()
        cplex_f = open('{}/p5_cplex_model_{}_2.lp'.format(cplex_models_path, test_num), mode='rb+')
        cplex_f.seek(-1, os.SEEK_END)
        cplex_f.truncate()
        cplex_f = open('{}/p5_cplex_model_{}_2.lp'.format(cplex_models_path, test_num), mode='a')
        cplex_f.write("]/2 \n")

        # contraint 1 --------------------------------------------------------------------------------------------

        print("Generating mapping constraints")
        cplex_f.write("\nSubject To \n")
        for u in set_state + set_replica:
            c_name = "c1_{}".format(u)
            cplex_f.write(" {}:  ".format(c_name))
            for i in set_PM:
                cplex_f.write(" x_({},{}) +".format(i, u))

            cplex_f.close()
            cplex_f = open('{}/p5_cplex_model_{}_2.lp'.format(cplex_models_path, test_num), mode='rb+')
            cplex_f.seek(-2, os.SEEK_END)
            cplex_f.truncate()
            cplex_f = open('{}/p5_cplex_model_{}_2.lp'.format(cplex_models_path, test_num), mode='a')
            cplex_f.write(" = 1\n")

        # contraint 2 --------------------------------------------------------------------------------------------
        print("Generating capacity constraints")
        for i in set_PM:
            c_name = "c2_{}".format(i)
            cplex_f.write(" {}:  ".format(c_name))
            for u in set_state + set_replica:
                cplex_f.write("{} x_({},{}) +".format(s[u], i, u))
            cplex_f.close()
            cplex_f = open('{}/p5_cplex_model_{}_2.lp'.format(cplex_models_path, test_num), mode='rb+')
            cplex_f.seek(-2, os.SEEK_END)
            cplex_f.truncate()
            cplex_f = open('{}/p5_cplex_model_{}_2.lp'.format(cplex_models_path, test_num), mode='a')
            cplex_f.write(" <= {}\n".format(c[i]))

        # contraint 3 --------------------------------------------------------------------------------------------
        print("Generating AA constraints")
        for i in set_PM:
            if "server" in i:
                for u, v in AA:
                    c_name = "c3_{}_{}_in_{}".format(u, v, i)
                    cplex_f.write(" {}:  ".format(c_name))
                    cplex_f.write(" x_({},{}) + x_({}, {}) <= 1\n".format(i, u, i, v))

        # contraint 4 --------------------------------------------------------------------------------------------
        print("Generating NF mapping constraints")
        for function in set_nf:
            for server in set_PM:
                c_name = "c4_{}_in_{}".format(function, server)
                try:
                    if M[function] == server:
                        cplex_f.write(" {}:  ".format(c_name))
                        cplex_f.write(" x_({},{}) = 1\n".format(server, function))
                    else:
                        cplex_f.write(" {}:  ".format(c_name))
                        cplex_f.write(" x_({},{}) = 0\n".format(server, function))
                except:
                    cplex_f.write(" {}:  ".format(c_name))
                    cplex_f.write(" x_({},{}) = 0\n".format(server, function))

        # contraint 5 --------------------------------------------------------------------------------------------
        def for_multiprocessing(list, from_, to_, test_num, process_id, cplex_models_path):
            print("Starting process {}, from: {}, to:{}".format(process_id, from_, to_))
            c5_f = open('{}/c5_testnum{}_tmp{}_2.txt'.format(cplex_models_path, test_num, process_id), mode='a')
            start = from_
            for i, j in list[from_:to_]:
                if (start % 10000) == 0:
                    print("{}: {}".format(process_id, start))
                c_name = "c5_({},{})_({},{})_0".format(i[0], i[1], j[0], j[1])
                c5_f.write(" {}:  ".format(c_name))
                c5_f.write(" y_({},{})_({},{}) >= 0 \n".format(i[0], i[1], j[0], j[1]))

                c_name = "c5_({},{})_({},{})_1".format(i[0], i[1], j[0], j[1])
                c5_f.write(" {}:  ".format(c_name))
                c5_f.write(
                    " y_({},{})_({},{}) - x_({},{}) - x_({},{}) >= -1 \n".format(i[0], i[1], j[0], j[1], i[0], i[1],
                                                                                 j[0], j[1]))
                start += 1
            c5_f.close()
            print("Ending process {}".format(process_id))

        print(datetime.datetime.now())
        print("Generating QP -> ILP transformation constraints")
        index_set = set()
        for i in set_PM:
            for u in set_state + set_replica + set_nf:
                index_set.add((i, u))
        index_combinations = list(itertools.permutations(index_set, 2))

        index_combinations_size = len(index_combinations)
        print("Size of this contraints: {}".format(index_combinations_size))

        from_to_list = []
        core_num = 10
        core_job_count = len(index_combinations) / 10
        for i in range(core_num):
            from_ = i * core_job_count
            to_ = (i + 1) * core_job_count
            if i == core_num - 1:
                to_ = index_combinations_size
            from_to_list.append((from_, to_))

        import multiprocessing
        processes = []
        for i in range(0, core_num):
            p = multiprocessing.Process(target=for_multiprocessing, args=(
                index_combinations, from_to_list[i][0], from_to_list[i][1], test_num, i, cplex_models_path))
            processes.append(p)
            p.start()

        for process in processes:
            process.join()

        tempfiles = ["{}/c5_testnum{}_tmp{}_2.txt".format(cplex_models_path, test_num, i) for i in range(core_num)]
        for tempfile in tempfiles:
            #print("Adding file {}".format(tempfile))
            tmp_f = open(tempfile, "r")
            cplex_f.write(tmp_f.read())

        for tempfile in tempfiles:
            os.remove(tempfile)

        # contraint 6 --------------------------------------------------------------------------------------------
        print("Generating 'Does it matter?' constraints")
        for u in (set_state + set_nf + set_replica):
            for v in (set_state + set_nf + set_replica):
                if u != v:
                    if is_OL(u, v, OL):
                        c_name = "c6_({},{})_0".format(u, v)
                        cplex_f.write("\n {}:  ".format(c_name))
                        first = True
                        for i, j in get_OLs(u, v, OL):

                            if first:
                                cplex_f.write(" z_({},{})".format(i, j))
                                first = False
                            else:
                                cplex_f.write(" + z_({},{})".format(i, j))
                        cplex_f.write(" = 1 \n")
                    else:
                        c_name = "c6_({},{})_1".format(u, v)
                        if "function" in u and "replica" in v:
                            cplex_f.write("\n {}:  ".format(c_name))
                            cplex_f.write(" z_({},{}) = 0".format(u, v))
                        elif "replica" in u and "state" in v:
                            cplex_f.write("\n {}:  ".format(c_name))
                            cplex_f.write(" z_({},{}) = 0".format(u, v))
                        else:
                            cplex_f.write("\n {}:  ".format(c_name))
                            cplex_f.write(" z_({},{}) = 1".format(u, v))

        # Bounds --------------------------------------------------------------------------------------------
        cplex_f.write("\nBounds\n")
        for i in set_PM:
            for u in set_state + set_replica + set_nf:
                cplex_f.write("0 <= x_({},{}) <= 1\n".format(i, u))

        index_set = set()
        for i in set_PM:
            for u in set_state + set_replica + set_nf:
                index_set.add((i, u))
        index_permutations = list(itertools.permutations(index_set, 2))
        for i, j in index_permutations:
            cplex_f.write("0 <= y_({},{})_({},{}) <= 1\n".format(i[0], i[1], j[0], j[1]))

        index_permutations = list(itertools.permutations((set_state + set_nf + set_replica), 2))
        for u, v in index_permutations:
            cplex_f.write("0 <= z_({},{}) <= 1\n".format(u, v))

        # Binaries --------------------------------------------------------------------------------------------
        cplex_f.write("\nBinaries\n")
        for i in set_PM:
            for u in set_state + set_replica + set_nf:
                cplex_f.write(" x_({},{})\n".format(i, u))

        index_set = set()
        for i in set_PM:
            for u in set_state + set_replica + set_nf:
                index_set.add((i, u))
        index_permutations = list(itertools.permutations(index_set, 2))
        for i, j in index_permutations:
            cplex_f.write(" y_({},{})_({},{})\n".format(i[0], i[1], j[0], j[1]))

        index_permutations = list(itertools.permutations((set_state + set_nf + set_replica), 2))
        for u, v in index_permutations:
            cplex_f.write(" z_({},{})\n".format(u, v))

        time.sleep(2)
        cplex_f.write("End\n")
        cplex_f.close()
        ########################################################################################################

    if not os.path.isfile(CPLEX_PATH):
        raise RuntimeError('CPLEX does not exist ({})'.format(CPLEX_PATH))

    subprocess.call("{} -c 'read {}/p5_cplex_model_{}_2.lp' 'write {}/p5_cplex_model_{}_2.sav sav'".format(
            CPLEX_PATH, cplex_models_path, test_num, cplex_models_path, test_num), shell=True)

    t1 = datetime.datetime.now()
    cost = 0
    mapping_result = {i: "" for i in set_state + set_nf + set_replica}

    if locally:
        # solving problem in locally
        print("\n\nSolving the problem locally - 2")
        subprocess.call(
            "{} -c 'read {}/p5_cplex_model_{}_2.mps' 'optimize' 'write {}/p5_cplex_result_{}_2 sol'".format(
                CPLEX_PATH, cplex_models_path, test_num, results_path, test_num), shell=True)
    else:
        print("\n\nSolving the problem remotely in the IBM cloud - 2")
        if not os.path.isfile("{}/p5_cplex_result_{}_2".format(results_path, test_num)):
            client = JobClient("https://api-oaas.docloud.ibmcloud.com/job_manager/rest/v1/",
                               "api_e7f3ec88-92fd-4432-84d7-f708c4a33132")
            print(
                "You can check the status of the problem procesing here: https://dropsolve-oaas.docloud.ibmcloud.com/dropsolve")
            resp = client.execute(input=["{}/p5_cplex_model_{}_2.sav".format(cplex_models_path, test_num)],
                                  output="{}/p5_cplex_result_{}_2".format(results_path, test_num))

            if resp.job_info["solveStatus"] == "INFEASIBLE_SOLUTION":
                print("There is no valid mapping!")
                return 0

    def is_json_file(report_input_file):
        with open(report_input_file) as unknown_file:
            c = unknown_file.read(1)
            if c != '<':
                return True
            return False

    t2 = datetime.datetime.now()
    if is_json_file("{}/p5_cplex_result_{}_2".format(results_path, test_num)):
        with open("{}/p5_cplex_result_{}_2".format(results_path, test_num)) as f:
            result = json.load(f)

        for i in result["CPLEXSolution"]["variables"]:
            if ("x_" in list(i["name"])) and i["value"] == str(1):
                print("{} = 1".format(i["name"]))
                server = i["name"].split(',')[0][3:]
                ve = i["name"].split(',')[1][:-1]
                mapping_result[ve] = server

                print("*** Delay cost: {} ***".format(result["CPLEXSolution"]["header"]["objectiveValue"]))
                cost = result["CPLEXSolution"]["header"]["objectiveValue"]

    else:
        with open("{}/p5_cplex_result_{}_2".format(results_path, test_num), 'r') as file:
            xml_result = file.read().replace('\n', '')
        result = xmltodict.parse(xml_result)
        print("*** Delay cost: {} ***".format(result["CPLEXSolution"]["header"]["@objectiveValue"]))
        cost = result["CPLEXSolution"]["header"]["@objectiveValue"]


    print("RUNNING TIME: {}".format(t2 - t1))
    return cost, mapping_result
