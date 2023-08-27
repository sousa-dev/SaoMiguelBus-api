import json
groups = json.loads(open("scripts/groups.json", "r").read())

for group in groups.keys():
    stops = groups[group]
    print("Name: ", group.lower())
    #stop1,stop2,stop3,stop4
    stop_string = ",".join(stops)
    print(stop_string)
    input()
