#!/usr/bin/python3


import os 
import multiprocessing
import argparse


plane_lists = {

    "Augusta" : [33.3699, -81.9645],
    "Columbia" : [33.961436,   -81.143562],
    "Orange" : [33.599107, -81.030564 ],
    "Gap" : [33.402789, -81.570110],
    "Gap2" : [33.794773, -81.518865]
}

def plane(lat, long):
    os.system("python3 flight370.py --host 10.50.172.24  --aircraft 12 --lat {} --long {}".format(str(lat), str(long)))

bees = []

parser = argparse.ArgumentParser(description='Not Today')
parser.add_argument('--dos', default=False, help="--dos=True to see the magic <3")
args = parser.parse_args()

if args.dos == True:
    while True:
        for k, v in plane_lists.items():
            p = multiprocessing.Process(target=plane, args=(plane_lists[k][0], plane_lists[k][1]))
            bees.append(p)
            p.start()
else:
    for k, v in plane_lists.items():
        p = multiprocessing.Process(target=plane, args=(plane_lists[k][0], plane_lists[k][1]))
        bees.append(p)
        p.start()    
