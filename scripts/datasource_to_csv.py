from sys import argv
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
    pass

def main():
    """
    Main function
    """
    #TODO: Get input, output files and entity from command line

    input = argv[1]
    output = argv[2]
    entity = argv[3]

    return stops_to_csv(input, output) if entity == "stops" else routes_to_csv(input, output)
if __name__ == '__main__':
    main()