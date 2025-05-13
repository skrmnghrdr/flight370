#!/usr/bin/python3



import os 
import multiprocessing

plane_lists = {

    "Augusta" : [33.3699, -81.9645],
    "Columbia" : [33.961436,   -81.143562],
    "Orange" : [33.599107, -81.030564 ]
}

def plane(lat, long):
    os.system("python3 flight370.py --host 10.50.172.24  --aircraft 100 --lat {} --long {}".format(str(lat), str(long)))

bees = []

while True:
    for k, v in plane_lists.items():
        p = multiprocessing.Process(target=plane, args=(plane_lists[k][0], plane_lists[k][1]))
        bees.append(p)
        p.start()

