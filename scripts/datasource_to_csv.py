from sys import argv

def print_usage():
    """
    Print usage
    """
    print("Usage: python3 datasource_to_csv.py <input_file> <output_file> <entity>")
    print("<entity> can be either 'stops' or 'routes'")
    print("Example: python3 datasource_to_csv.py data/stops.txt out/stops.csv stops")
    print("Example: python3 datasource_to_csv.py data/avm_routes.txt out/routes.csv routes")

def stops_to_csv(input, output):
    """
    Write stops to csv
    """
    with open(input, 'r') as f_in:
        with open(output, 'w') as f_out:
            f_out.write("name, lat, long\n")
            for line in f_in:
                clean_line = line.rstrip().replace("Stop", "").replace("(", "").replace(")", "").replace("\"", "").replace("Location", "")
                f_out.write(clean_line + "\n")



def routes_to_csv(input, output):
    """
    Write routes to csv
    """
    routes = []
    route = -1
    type_of_day = None
    details = []
    with open(input, 'r') as f_in:
        with open(output, 'w') as f_out:
            f_out.write("stop, times, type_of_day\n")
            for line in f_in:
                if line.startswith("route"):
                    type_of_day = None
                    route = line.split()[-1].replace("\"", "")
                    details = [route]
                elif line.startswith("getStop"):
                    clean_line = line.rstrip().replace("getStop", "").replace("(", "").replace(")", "").replace("\"", "").replace("to listOf", ",")
                    temp_details = clean_line.strip().split(',')
                    details.append([detail.strip() for detail in temp_details if detail != ""])
                elif "TypeOfDay" in line:
                    type_of_day = line.split(",")[1].replace("TypeOfDay.", "").strip()
                    details.append(type_of_day)

                    routes.append(details)

                    details = [route]
                    type_of_day = None
    for route in routes:
        #TODO: Process route to store it on csv file
        print(route)

def main():
    """
    Main function
    """
    if len(argv) == 1 or argv[1] == "-h" or argv[1] == "--help" :
        print_usage()
        exit(0)

    input = argv[1]
    output = argv[2]
    entity = argv[3]

    return stops_to_csv(input, output) if entity == "stops" else routes_to_csv(input, output)

if __name__ == '__main__':
    main()