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
    'justFriday': {
        "pt": "Só à Sexta-Feira", 
        "en": "Just Friday",
        "es": "Solo viernes",
        "fr": "Juste vendredi",
        "de": "Nur Freitag"
        },
    'r318': {
        "pt": "a) De Segunda a Quinta // b) Só à Sexta", 
        "en": "a) From Monday to Thursday // b) Just Friday",
        "es": "a) De lunes a jueves // b) Solo viernes",
        "fr": "a) Du lundi au jeudi // b) Uniquement le vendredi",
        "de": "a) Von Montag bis Donnerstag // b) Nur am Freitag"
        },
    'avDHenrique': {
        "pt": "Saída no lado Sul da Av. Infante D.Henrique", 
        "en": "This service starts in the South Side of Av. Infante D.Henrique.",
        "es": "Este servicio se inicia en el lado sur de la Av. Infante D. Henrique.",
        "fr": "Ce service commence dans le côté sud de l'Av. Infante D. Henrique.",
        "de": "Dieser Service beginnt in der Südseite der Av. Infante D. Henrique."
        },
    'tourismOffice': {
        "pt": "Saída junto ao Posto de Turismo", 
        "en": "This service starts next to the Tourism Office.",
        "es": "Este servicio comienza junto a la Oficina de Turismo.",
        "fr": "Ce service démarre à côté de l'Office de Tourisme.",
        "de": "Dieser Service beginnt neben dem Tourismusbüro."
        },
    'school': {
        "pt": "Período Escolar", 
        "en": "School Period",
        "es": "Periodo Escolar",
        "fr": "Période Scolaire",
        "de": "Schulzeit"
        },
    'normal': {
        "pt": "Período Normal", 
        "en": "Normal Period",
        "es": "Periodo normal",
        "fr": "Période normale",
        "de": "Normale Periode"
        },
    'julyToSep': {
        "pt": "De 15 de julho até 15 de setembro", 
        "en": "From July 15th to September 15th",
        "es": "Del 15 de julio al 15 de septiembre",
        "fr": "Du 15 juillet au 15 septembre",
        "de": "Vom 15. Juli bis 15. September"
        },
    'onlySchool': {
        "pt": "Só em período escolar", 
        "en": "Only School Period",
        "es": "Solo período escolar",
        "fr": "Période scolaire uniquement",
        "de": "Nur Schulzeit"
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
            f_out.write("id; route; times; type_of_day; information\n")
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
                        function = line.rstrip().split(',')[-2].split('.')
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