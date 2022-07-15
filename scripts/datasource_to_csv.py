from sys import argv

FUNC_NAME_TO_INFO = { 
    'rossioBanif': {
        "pt": "Passagem em 'Capelas - Rossio' junto ao Santander", 
        "en": "Bus Stop in 'Capelas - Rossio' near Santander",
        "es": "Parada de autobús en 'Capelas - Rossio' cerca de Santander",
        "fr": "Arrêt de bus à 'Capelas - Rossio' près de Santander",
        "de": "Bushaltestelle in 'Capelas - Rossio' bei Santander"
        },
    'rossioCaixa':  {
        "pt": "Passagem em 'Capelas - Rossio' junto à escola", 
        "en": "Bus Stop in 'Capelas - Rossio' near the School",
        "es": "Parada de autobús en 'Capelas - Rossio' cerca de la escuela",
        "fr": "Arrêt de bus à 'Capelas - Rossio' près de l'école",
        "de": "Bushaltestelle in 'Capelas - Rossio' in der Nähe der Schule"
        },
    'fsaobras':  {
        "pt": "Saída no Forte de São Brás", 
        "en": "This service starts at Forte de São Brás",
        "es": "Este servicio comienza en Forte de São Brás",
        "fr": "Ce service commence à Forte de São Brás",
        "de": "Dieser Service beginnt bei Forte de São Brás"
        },
}

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
    func_name = None
    with open(input, 'r') as f_in:
        with open(output, 'w') as f_out:
            f_out.write("id; stop; times; type_of_day; information\n")
            for line in f_in:
                if line.startswith("route"):
                    type_of_day = None
                    func_name = None
                    route = line.split()[-1].replace("\"", "")
                    details = [route]
                elif line.startswith("getStop"):
                    clean_line = line.rstrip().replace("getStop", "").replace("(", "").replace(")", "").replace("\"", "").replace("to listOf", ",")
                    temp_details = clean_line.strip().split(',')
                    details.append([detail.strip() for detail in temp_details if detail != ""])
                elif "TypeOfDay" in line:
                    if "Functions()" in line:
                        function = line.split(',')[-1].split('.')
                        if len(function) > 1:
                            func_name = function[1].split('(')[0]
                            func_name = FUNC_NAME_TO_INFO[func_name]
                    type_of_day = line.split(",")[1].replace("TypeOfDay.", "").strip()
                    details.append(type_of_day)
                    details.append(func_name)

                    routes.append(details)

                    details = [route]
                    type_of_day = None
                    func_name = None
            for route in routes:
                stop_times = {}
                route_id = route[0]
                stops = route[1:-2]
                for stop in stops:
                    stop_times[stop[0]] = stop[1:]
                day = route[-2]
                info = route[-1]
                for i in range(len(list(stop_times.values())[0])):
                    times = {}
                    for stop in stop_times:
                        if stop_times[stop][i] != "---":
                            times[stop] = stop_times[stop][i]
                    f_out.write(f"{route_id+'-'+list(times.values())[0]};{route_id};{times};{day};{info}\n")
                #print(f"{route_id};{stop_times};{day};{info}\n")
                #f_out.write(f"{route_id};{stops};{day};{info}\n")

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

    try:
        return stops_to_csv(input, output) if entity == "stops" else routes_to_csv(input, output)
    except Exception as e:
        print("ERROR: " + str(e))
        print_usage()
        exit(1)

if __name__ == '__main__':
    main()