import ConfigParser
import os
import os.path
import sys

import scipy as sp

from chemex import parsing


def create_par_list_to_fit(par_filename, data):
    """
    Create and set the list of parameters to fit.
    """

    # Create parameters needed to fit the data
    par, par_indexes, par_fixed = create_fitting_parameters_array(data)

    # Trim data
    data = trim_datasets_using_par(data, par_indexes)

    # Set the parameters to their default value as defined in the 'par'
    # file
    par, par_fixed = read_par(par_filename, par, par_indexes, par_fixed)

    # Filter Data
    data = [data_pt for data_pt in data if
            not data_pt.filter(par, par_indexes, par_fixed)]

    return par, par_indexes, par_fixed, data


def create_fitting_parameters_array(data):
    """
    Creates the array of parameters that will be used for the fitting
    along with the dictionary that associate the name and the index of each
    parameter in the array.
    """

    parameters_to_fit = set()
    parameters_to_fix = set()

    for data_point in data:
        parameters_to_fit.update(data_point.get_fitting_parameter_names())
        parameters_to_fix.update(data_point.get_fixed_parameter_names())

    par = sp.zeros(len(parameters_to_fit))

    par_indexes = dict(
        (par_name, index) for index, par_name in enumerate(parameters_to_fit))

    default_val = None

    parameters_to_fix = parameters_to_fix - parameters_to_fit

    par_fixed = dict(
        (par_name, default_val)
        for index, par_name in enumerate(parameters_to_fix)
    )

    return par, par_indexes, par_fixed


def trim_datasets_using_par(data, par_indexes):
    """
    Removes all the data points needing more fitting parameters than available.
    """

    parameters_to_fit = set(par_indexes.keys())

    trimmed_data = list()

    for data_point in data:
        if data_point.get_fitting_parameter_names() <= parameters_to_fit:
            trimmed_data.append(data_point)

    return trimmed_data


def read_par(input_file, par, par_indexes, par_fixed):
    """
    Read the file containing the initial guess for the fitting parameters.
    """

    print("\n[{:s}]".format(input_file))
    concern = False

    # Parse the config file
    parameters_cfg = ConfigParser.SafeConfigParser()

    if os.path.isfile(input_file):

        try:
            parameters_cfg.read(input_file)

        except ConfigParser.MissingSectionHeaderError:
            exit("You are missing a section heading (default?) in {:s}\n"
                 .format(input_file))

        except ConfigParser.ParsingError:
            exit("Having trouble reading your parameter file, have you "
                 "forgotten '=' signs?\n{:s}".format(sys.exc_info()[1]))

    else:
        exit("The file \'{}\' is empty or does not exist!\n".format(input_file))

    # Container for the default values
    starting_parameters = list()

    # this assumes that the first key of each long key is the real parameter
    #  name
    # ... can this be untrue?
    long_par_names = set(par_indexes) | set(par_fixed)
    short_long_par_names = {}

    for key in long_par_names:

        key_str = set([str(_) for _ in key])
        short_long_par_names.setdefault(key[0], set()).update(key_str)

    # Default parameters
    sections = set(parameters_cfg.sections())

    if 'default' in sections:
        section_default = 'default'

    elif 'global' in sections:
        section_default = 'global'

    else:
        exit("Section \'default\' must be present in {:s} (formerly 'global')\n"
             .format(input_file))

    for par_name, val in parameters_cfg.items(section_default):

        par_set = set([token.strip() for token in par_name.split(',')])

        if len(par_set & set(short_long_par_names)) != 1:
            print(' ! {:s} is not an appropriate default or may be unnecessary.'
                  ' Ignoring entry.'.format(str(par_name)))
            concern = True

        else:
            val = val.strip().split()[0]
            starting_parameters.append((par_set, val))

    parameters_cfg.remove_section(section_default)

    # Local parameters
    for section in parameters_cfg.sections():

        par_name = [token.strip().lower() for token in section.split(',')]

        if par_name[0] not in short_long_par_names:
            print(" ! [{:s}] does not match any of your data (possibly ignored "
                  "above).".format(section))
            concern = True
            continue

        elif not set(par_name) <= short_long_par_names[par_name[0]]:
            print(" ! [{:s}] does not match any of your data. No parameter will"
                  " be updated.".format(section))
            concern = True
            continue

        num_items = 0
        num_updates = 0

        for key, val in parameters_cfg.items(section):

            if 'file' in key:

                file_names = val.strip('\n ').split('\n')

                for filename in file_names:

                    if not os.path.isabs(filename):
                        filename = os.path.join(os.path.dirname(input_file),
                                                filename)

                    parameters = read_parameter_file(filename, par_name)
                    starting_parameters.extend(parameters)

                    num_items += len(parameters)
                    for a_par_name, _ in parameters:
                        if set(a_par_name) <= short_long_par_names[par_name[0]]:
                            num_updates += 1

            else:

                # Just take the first value in case the file contain a value and
                # an uncertainty
                val = val.strip().split()[0]

                # The key is the resonance_id
                full_par_name = par_name + [key]
                starting_parameters.append((full_par_name, val))

                num_items += 1
                if set(full_par_name) <= short_long_par_names[full_par_name[0]]:
                    num_updates += 1

        if not num_updates and num_items:
            print(" ! No parameters updated in section [{:s}]!".format(section))
            print("   - Check that your names match your data files")
            concern = True

        elif num_updates <= num_items:
            print("  * {:d} out of {:d} parameters updated in section [{:s}]"
                  .format(num_updates, num_items, section))

    # Set parameters values to the default
    for par_name_1, val in starting_parameters:

        for par_name_2, index in par_indexes.items():
            par_name_2_str = [str(_) for _ in par_name_2]
            if set(par_name_1) <= set(par_name_2_str):
                par[index] = float(val)

        for par_name_2 in par_fixed:
            par_name_2_str = [str(_) for _ in par_name_2]
            if set(par_name_1) <= set(par_name_2_str):
                par_fixed[par_name_2] = float(val)

    # Check that fitting parameters are all initialized
    par_none = set()
    par_ngtv = set()

    for par_name, index in par_indexes.items():

        par_name_str = [str(_) for _ in par_name]

        if par[index] is None:
            par_none.add(par_name_str[0])

        elif par[index] < 0.0 and par_name_str[0].startswith('r_'):
            par_ngtv.add(','.join(par_name_str))

    # Check that fixed parameters are all initialized
    for par_name in par_fixed:

        par_name_str = [str(_) for _ in par_name]

        if par_fixed[par_name] is None:
            par_none.add(par_name_str[0])

        elif par_fixed[par_name] < 0.0 and par_name_str[0].startswith('r_'):
            par_ngtv.add(','.join(par_name_str))

    if len(par_ngtv):
        print(" ! Rates should not be negative!\n"
              "    {:s}".format("\n    ".join(sorted(par_ngtv))))
        concern = True

    if len(par_none):
        exit(" -- Some parameters must be set!\n"
             "    {:s}".format(", ".join(sorted(par_none))))

    if concern:
        print('\n ! There are problems that require your attention')
    else:
        print('  * No major concerns found!')

    return par, par_fixed


def read_parameter_file(filename, par_name):
    """
    Reads a file containing values associated with a nucleus name.
    The file should be formatted like sparky peak lists.

    For example:
      * To set G23N to 105.0 and G23H to 8.0:
          G23N-H  105.0  8.0
      * To set a parameter depending on multiple nuclei, eg. G23N and G23H, to 1.0:
          G23N-H  -93.0
    """

    try:
        raw_data = sp.genfromtxt(filename, dtype=None)
    except IOError:
        exit('The file \'{}\' is empty or does not exist!\n'.format(filename))

    # Hack to solve the problem of 0d-array when 'filename' is a single line
    # file
    if raw_data.ndim == 0:
        raw_data = sp.array([raw_data, ])

    parameters = []

    for line in raw_data:

        if line[0] in ['Assignment', '?-?']:
            continue

        assignment = parsing.parse_assignment(line[0])

        if len(assignment) == len(line) - 1:
            for index, an_assignment in enumerate(assignment, 1):
                name = parsing.assignment_name([an_assignment])
                full_par_name = par_name + [name]
                parameters.append((full_par_name, line[index]))

        elif len(line) == 2:
            name = parsing.assignment_name(assignment)
            full_par_name = par_name + [name]
            parameters.append((full_par_name, line[1]))

        else:

            error_message = '\n'.join(
                ["Problem reading the parameter file '{}'.".format(filename),
                 "The number of columns does not match to the number of nuclei"
                 " contained in the assignment:"])
            exit(error_message)

    return parameters


def main():
    pass


if __name__ == '__main__':
    main()
