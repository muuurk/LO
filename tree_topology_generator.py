#!/usr/bin/env python

import argparse
import matplotlib.pyplot as plt
import networkx as nx
from networkx.readwrite import json_graph
import random
import json
import sys

def parse_args():

    possible_problems = ["p3", "p5"]
    parser = argparse.ArgumentParser()
    parser.add_argument('-s','--server_num', type=int, action='store',dest='servers', default=10, help='number of servers in a rack')
    parser.add_argument('-r', '--rack_num', type=int, action='store', dest='racks', default=10, help='number of racks')
    parser.add_argument('-f', '--function_num', type=int, action='store', dest='Fs', default=400, help='number of functions')
    parser.add_argument( '--state_min', type=int, action='store', dest='state_min', default=1, help='minimum number of states for a function')
    parser.add_argument('--state_max', type=int, action='store', dest='state_max', default=5, help='maximum number of states for a function')
    parser.add_argument('--replica_min', type=int, action='store', dest='state_min', default=1,
                        help='minimum number of replicas for a function')
    parser.add_argument('--replica_max', type=int, action='store', dest='state_max', default=5,
                        help='maximum number of replicas for a function')

    parser.add_argument('-p', '--problem', type=str, action='store', dest='problem', default="p3",
                        help='ID of the problem to solve.\n Possible problems: {}'.format(possible_problems))
    parser.add_argument('-o', '--out', action='store',dest='outputID',default="", help='ID in the outputfile')

    args = parser.parse_args()
    if args.problem not in possible_problems:
        print("Unexpected problem parameter. Please choose from the followings:{}".format(possible_problems))
        sys.exit()

    return args


def generating_topology(args):
    G_topology = nx.Graph()

    # Generating topology
    G_topology.add_node("core", capacity=0, NFs=[])
    for r in range(args.racks):
        G_topology.add_node("tor_{}".format(r), capacity=0, NFs=[])
        G_topology.add_edge("tor_{}".format(r), "core", delay=1)
        for s in range(args.servers):
            G_topology.add_node("server_{}_{}".format(r, s), capacity=8000, NFs=[])
            G_topology.add_edge("server_{}_{}".format(r, s), "tor_{}".format(r), delay=1)

    # Mapping NFs
    for nf in range(args.Fs):
        rack = random.randint(0, args.racks - 1)
        server = random.randint(0, args.servers - 1)

        f_name = "function_{}".format(nf)
        G_topology.nodes["server_{}_{}".format(rack, server)]["NFs"].append(f_name)

    return G_topology

def generating_request(args):

    G_request = nx.Graph()
    state_id = 0

    for nf in range(args.Fs):
        f_name = "function_{}".format(nf)
        G_request.add_node(f_name)

        state_num = random.randint(2,10)
        for s in range(state_num):
            G_request.add_node("state_{}".format(state_id), size=random.randint(100,400))
            G_request.add_edge("state_{}".format(state_id), f_name)
            state_id += 1

    for i in range(1000):
        picked_state = "state_{}".format(random.randint(0,state_id-1))
        picked_function = "function_{}".format(random.randint(0,args.Fs-1))
        G_request.add_edge(picked_state, picked_function)

    # print edges
    degrees = {}
    for i in range(state_id):

        degree = G_request.degree["state_{}".format(i)]
        try:
            degrees[degree] +=1
        except:
            degrees[degree] = 1

    for key, value in degrees.iteritems():
        print("{}:\t{}".format(key,value))

    return G_request

def generating_requests_for_p5(args):

    G_request = nx.DiGraph()
    state_id = 0

    for nf in range(args.Fs):
        f_name = "function_{}".format(nf)
        G_request.add_node(f_name)

        state_num = random.randint(args.state_min,args.state_max)
        for s in range(state_num):
            G_request.add_node("state_{}".format(state_id), size=random.randint(100,400), replicas=[])
            # edge type: 1-reading, 2-writing, 3-both
            edge_type = random.randint(1,3)
            if edge_type == 1:
                G_request.add_edge("state_{}".format(state_id), f_name)
            elif edge_type == 2:
                G_request.add_edge(f_name, "state_{}".format(state_id))
            elif edge_type == 3:
                G_request.add_edge("state_{}".format(state_id), f_name)
                G_request.add_edge(f_name, "state_{}".format(state_id))
            state_id += 1

    replica_id = 0
    for i in range(state_id):

        picked_state = "state_{}".format(i)
        replica = random.randint(0,3)
        for j in range(replica):
            G_request.add_node("replica_{}".format(replica_id), size=G_request.nodes[picked_state]["size"])
            G_request.nodes[picked_state]["replicas"].append("replica_{}".format(replica_id))
            G_request.add_edge( picked_state, "replica_{}".format(replica_id))

            nf_neighbors = [i for i in list(G_request.neighbors(picked_state)) if "function" in i]
            for nf in nf_neighbors:
                try:
                    G_request[picked_state][nf]
                    G_request.add_edge("replica_{}".format(replica_id), nf)
                except:
                    pass
            replica_id += 1


    # print edges
    function_degrees = {}
    replica_degrees = {}
    for i in range(state_id):

        function_degree = 0
        replica_degree = 0
        for n in G_request.neighbors("state_{}".format(i)):
            if "function" in n:
                function_degree += 1
            elif "replica" in n:
                replica_degree += 1

        try:
            function_degrees[function_degree] += 1
        except:
            function_degrees[function_degree] = 1
        try:
            replica_degrees[replica_degree] += 1
        except:
            replica_degrees[replica_degree] = 1

    print("Function degree:")
    for key, value in function_degrees.iteritems():
        print("{}:\t{}".format(key,value))

    print("Replica degree:")
    for key, value in replica_degrees.iteritems():
        print("{}:\t{}".format(key, value))

    return G_request


if __name__ == '__main__':
    args = parse_args()

    G_topology = generating_topology(args)
    if args.problem == "p3":
        G_request = generating_request(args)
    elif args.problem == "p5":
        G_request = generating_requests_for_p5(args)
    else:
        raise Exception("Given problem ID is not exist!")

    topology_json = json_graph.node_link_data(G_topology)
    with open('graph_models/{}_topology_graph_{}.json'.format(args.problem, args.outputID), 'w') as outfile:
        json.dump(topology_json, outfile)

    request_json = json_graph.node_link_data(G_request)
    with open('graph_models/{}_request_graph_{}.json'.format(args.problem, args.outputID), 'w') as outfile:
        json.dump(request_json, outfile)

    # Drawing the graph
    # nx.draw(G_request, with_labels=True)
    # plt.show()