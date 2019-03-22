#!/usr/bin/env python

import argparse
import matplotlib.pyplot as plt
import networkx as nx
from networkx.readwrite import json_graph
import random
import json

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-s','--server_num', type=int, action='store',dest='servers', default=10, help='number of servers in a rack')
    parser.add_argument('-r', '--rack_num', type=int, action='store', dest='racks', default=10, help='number of racks')
    parser.add_argument('-f', '--function_num', type=int, action='store', dest='Fs', default=400, help='number of functions')
    parser.add_argument('-o', '--out', action='store',dest='outputID',default="", help='ID in the outputfile')

    return parser.parse_args()


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


if __name__ == '__main__':
    args = parse_args()

    G_topology = generating_topology(args)
    G_request = generating_request(args)

    topology_json = json_graph.node_link_data(G_topology)
    with open('graph_models/topology_graph_{}.json'.format(args.outputID), 'w') as outfile:
        json.dump(topology_json, outfile)

    request_json = json_graph.node_link_data(G_request)
    with open('graph_models/request_graph_{}.json'.format(args.outputID), 'w') as outfile:
        json.dump(request_json, outfile)

    # Drawing the graph
    #nx.draw(G_request, with_labels=True)
    #plt.show()