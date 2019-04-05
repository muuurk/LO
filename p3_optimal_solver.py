#!/usr/bin/python
# ---------------------------------------------------------------------------
# File: p3_optimal_solver.py
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
import subprocess
import xmltodict

def merge_two_dicts(x, y):
    z = x.copy()   # start with x's keys and values
    z.update(y)    # modifies z with y's keys and values & returns None
    return z


def read_json_file(filename):
    with open(filename) as f:
        js_graph = json.load(f)
    return json_graph.node_link_graph(js_graph)

def generating_delay_matrix(graph):
    d= {(i, j): 1000000 for i in list(graph.nodes) for j in list(graph.nodes)}
    for i in list(graph.nodes):
        for j in list(graph.nodes):
            path_length, path_nodes, negative_cycle = bf.bellman_ford(graph, source=i, target=j, weight="delay")
            d[(i,j)] = path_length
    return d

def generating_req_adj(nfs, states, graph):
    adj = {(j,i): 0 for j in list(nfs) for i in list(states)}
    for j in list(nfs):
        for i in list(states):
            try:
                graph[j][i]
                adj[(j,i)] = 1
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
    vnfs = [n for n in graph.neighbors(state)]
    if vnfs == []:
        raise Exception("Given NF is not mapped into any of the PMs")
    else:
        return vnfs

def solving_placement_problem_from_file(topology_graph, request_graph, test_num, locally, CPLEX_PATH, cplex_models_path, results_path):

    if not os.path.isfile("./cplex_models/p3_cplex_model_{}.lp".format(test_num)):

        # Reading networkx file
        G_topology = read_json_file(topology_graph)
        G_request = read_json_file(request_graph)

        set_PM = list(G_topology.nodes)
        set_state_or_nf = list(G_request.nodes)
        set_state, set_nf = [], []
        for i in set_state_or_nf:
            if "function" in i:
                set_nf.append(i)
            elif "state" in i:
                set_state.append(i)
        # TODO: Validating request graph
        for i in set_state:
            try:
                G_request.nodes[i]['size']
            except:
                RuntimeError("The given request graph is incorrect: State {} has no 'size' value".format(i))

        s = {i: G_request.nodes[i]['size'] for i in set_state}
        c = {i: G_topology.nodes[i]['capacity'] for i in set_PM}
        e_t = {i: G_topology.edges[i]['delay'] for i in list(G_topology.edges)}
        print("Generating delay matrix...")
        d = generating_delay_matrix(G_topology)
        print("Generating state-function adjacency matrix...")
        e_r = generating_req_adj(set_nf, set_state, G_request)
        # e_r = generating_req_adj(set_state, set_nf, G_request)
        print("Generating Function mapping matrix...")
        M = generating_nf_mapping_matrix(G_topology)

        opt_model = cpx.Model(name="P3")

        # Binary variables
        print("Creating variables...")
        x_vars = {(i, u): opt_model.binary_var(name="x_{0}_{1}".format(i, u)) for i in set_PM for u in set_state}

        # == constraints
        print("Creating constraints 1...")
        for u in set_state:
            c_name = "c1_{}".format(u)
            tmp_constraints = { c_name : opt_model.add_constraint(ct=opt_model.sum(x_vars[i, u] for i in set_PM) == 1, ctname=c_name)}

        # <= constraints
        print("Creating constraints 2...")
        capacity_constraints = {}
        for i in set_PM:
            c_name = "c2_{}".format(i)
            tmp_constraints = {c_name: opt_model.add_constraint(ct=opt_model.sum(s[u] * x_vars[i, u] for u in set_state) <= c[i], ctname=c_name)}

        print("Creating Objective function...")
        print(datetime.datetime.now())

        # servers = [i for i in set_PM if "server" in i]
        # for i in servers:
        #     for u in set_state:
        #         connected_nfs = get_NF_of_state(G_request, u)
        #         for v in connected_nfs:
        #             objective = opt_model.sum(x_vars[i, u] * e_r[v, u] * d[i, M[v]])

        servers = [i for i in set_PM if "server" in i]
        objective = opt_model.sum(x_vars[i, u] * e_r[v,u] * d[i,M[v]] for i in servers for u in set_state for v in get_NF_of_state(G_request,u))

        # for minimization
        opt_model.minimize(objective)

        print("Exporting the problem")
        opt_model.export_as_lp(basename="p3_cplex_model_{}".format(test_num), path="./cplex_models")


    if locally:

        if not os.path.isfile(CPLEX_PATH):
            raise RuntimeError('CPLEX does not exist ({})'.format(CPLEX_PATH))

        # solving problem in locally
        t1 = datetime.datetime.now()
        print("\n\nSolving the problem locally")
        subprocess.call(
            "{} -c 'read {}/p3_cplex_model_{}.lp' 'optimize' 'write {}/p3_cplex_result_{} sol'".format(
                CPLEX_PATH, cplex_models_path, test_num, results_path, test_num), shell=True)
        t2 = datetime.datetime.now()

        with open("{}/p3_cplex_result_{}".format(results_path, test_num), 'r') as file:
            xml_result = file.read().replace('\n', '')
        result = xmltodict.parse(xml_result)
        print("\n\n*** Running time: {} ***".format(t2-t1))
        print("*** Delay cost: {} ***".format(result["CPLEXSolution"]["header"]["@objectiveValue"]))
        cost = result["CPLEXSolution"]["header"]["@objectiveValue"]

        return cost, t2-t1

    # solving with local cplex
    #print("Solving the problem locally")
    #print(datetime.datetime.now())
    #asd = opt_model.solve()
    else:

        # solving in the docplex cloud
        print("Solving the problem by the cloud")
        print(datetime.datetime.now())

        if not os.path.isfile("optimization_results/p3_cplex_result_{}.json".format(test_num)):
            client = JobClient("https://api-oaas.docloud.ibmcloud.com/job_manager/rest/v1/", "api_e7f3ec88-92fd-4432-84d7-f708c4a33132")
            print("You can check the status of the problem procesing here: https://dropsolve-oaas.docloud.ibmcloud.com/dropsolve")
            t1 = datetime.datetime.now()
            resp = client.execute(input=["./cplex_models/p3_cplex_model_{}.lp".format(test_num)], output="optimization_results/p3_cplex_result_{}.json".format(test_num))
            #resp = opt_model.solve(url="https://api-oaas.docloud.ibmcloud.com/job_manager/rest/v1/", key="api_e7f3ec88-92fd-4432-84d7-f708c4a33132")
            t2 = datetime.datetime.now()

            if resp.job_info["solveStatus"] == "INFEASIBLE_SOLUTION":
                    print("There is no valid mapping!")
                    return 0, t2-t1
            else:
                with open("./optimization_results/p3_cplex_result_{}.json".format(test_num)) as f:
                    result = json.load(f)
                    for i in result["CPLEXSolution"]["variables"]:
                        if i["value"] == str(1):
                            #print("{} = 1".format(i["name"]))
                            asd = 0
                    print("*** Delay cost: {} ***".format(result["CPLEXSolution"]["header"]["objectiveValue"]))
                    return result["CPLEXSolution"]["header"]["objectiveValue"], t2-t1
        else:

            with open("./optimization_results/p3_cplex_result_{}.json".format(test_num)) as f:
                result = json.load(f)
                for i in result["CPLEXSolution"]["variables"]:
                    if i["value"] == str(1):
                        #print("{} = 1".format(i["name"]))
                        asd = 0
                pass
                print("*** Delay cost: {} ***".format(result["CPLEXSolution"]["header"]["objectiveValue"]))
                return result["CPLEXSolution"]["header"]["objectiveValue"], 0


