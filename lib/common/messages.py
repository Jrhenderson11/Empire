"""

Common terminal messages used across Empire.

Titles, agent displays, listener displays, etc.

"""
from __future__ import print_function
from __future__ import absolute_import

from builtins import str
from builtins import range
import os
import time
import textwrap

# Empire imports
from . import helpers


###############################################################
#
# Messages
#
###############################################################

def title(version):
    """
    Print the tool title, with version.
    """
    print(r"""
          |\      _,,,---,,_
          /,`.-'`'    -.  ;-;;,_
         |,4-  ) )-,_. ,\ (  `'-'
        '---''(_/--'  `-'\_)  

            Kitty-Empire""")
    

def headless_title(version, num_modules, num_listeners, num_agents):
    """
    Print the tool title, with version.
    """
    print(r"""
          |\      _,,,---,,_
          /,`.-'`'    -.  ;-;;,_
         |,4-  ) )-,_. ,\ (  `'-'
        '---''(_/--'  `-'\_)  

            Kitty-Empire""")    
    print("       " + helpers.color(str(num_modules), "green") + " modules currently loaded\n")
    print("       " + helpers.color(str(num_listeners), "green") + " listeners currently active\n")
    print("       " + helpers.color(str(num_agents), "green") + " agents currently active\n\n")


def wrap_string(data, width=40, indent=32, indentAll=False, followingHeader=None):
    """
    Print a option description message in a nicely
    wrapped and formatted paragraph.

    followingHeader -> text that also goes on the first line
    """

    data = str(data)

    if len(data) > width:
        lines = textwrap.wrap(textwrap.dedent(data).strip(), width=width)

        if indentAll:
            returnString = ' ' * indent + lines[0]
            if followingHeader:
                returnString += " " + followingHeader
        else:
            returnString = lines[0]
            if followingHeader:
                returnString += " " + followingHeader
        i = 1
        while i < len(lines):
            returnString += "\n" + ' ' * indent + (lines[i]).strip()
            i += 1
        return returnString
    else:
        return data.strip()


def wrap_columns(col1, col2, width1=24, width2=40, indent=31):
    """
    Takes two strings of text and turns them into nicely formatted column output.

    Used by display_module()
    """

    lines1 = textwrap.wrap(textwrap.dedent(col1).strip(), width=width1)
    lines2 = textwrap.wrap(textwrap.dedent(col2).strip(), width=width2)

    result = ''

    limit = max(len(lines1), len(lines2))

    for x in range(limit):

        if x < len(lines1):
            if x != 0:
                result += ' ' * indent
            result += '{line: <0{width}s}'.format(width=width1, line=lines1[x])
        else:
            if x == 0:
                result += ' ' * width1
            else:
                result += ' ' * (indent + width1)

        if x < len(lines2):
            result += '  ' + '{line: <0{width}s}'.format(width=width2, line=lines2[x])

        if x != limit-1:
            result += "\n"

    return result


def display_options(options, color=True):
    """
    Take a dictionary and display it nicely.
    """
    for key in options:
        if color:
            print("\t%s\t%s" % (helpers.color('{0: <16}'.format(key), "green"), wrap_string(options[key])))
        else:
            print("\t%s\t%s" % ('{0: <16}'.format(key), wrap_string(options[key])))


def display_agents(agents):
    """
    Take a dictionary of agents and build the display for the main menu.
    """

    rowToggle = 0

    if len(agents) > 0:

        print('')
        print(helpers.color("[*] Active agents:\n"))
        print(" Name     La Internal IP     Machine Name      Username                Process            PID    Delay    Last Seen            Listener")
        print(" ----     -- -----------     ------------      --------                -------            ---    -----    ---------            ----------------")

        for agent in agents:
            if str(agent['high_integrity']) == '1' or agent['high_integrity'] is True:
                # add a * to the username if it's high integrity
                agent['username'] = '*' + str(agent['username'])
            if not agent['language'] or agent['language'] == '':
                agent['language'] = 'X'
            elif agent['language'].lower() == 'powershell':
                agent['language'] = 'ps'
            elif agent['language'].lower() == 'python':
                agent['language'] = 'py'
            else:
                agent['language'] = 'X'

            print(" %.8s %.2s %.15s %.17s %.23s %.18s %.6s %.8s %.31s %.16s" % ('{0: <8}'.format(agent['name']),
                                  '{0: <2}'.format(agent['language']),
                                  '{0: <15}'.format(str(agent['internal_ip']).split(" ")[0]),
                                  '{0: <17}'.format(str(agent['hostname'])),
                                  '{0: <23}'.format(str(agent['username'])),
                                  '{0: <18}'.format(str(agent['process_name'])),
                                  '{0: <6}'.format(str(agent['process_id'])),
                                  '{0: <8}'.format(str(agent['delay']) + "/"  +str(agent['jitter'])),
                                  '{0: <31}'.format(str(helpers.lastseen(agent['lastseen_time'], agent['delay'], agent['jitter']))),
                                  '{0: <16}'.format(str(agent['listener']))))

            # Skip rows for better readability
            rowToggle = (rowToggle + 1) % 3
            if rowToggle == 0:
                print()
        print('')
    else:
        print(helpers.color('[!] No agents currently registered'))


def display_agent(agent, returnAsString=False):
    """
    Display an agent all nice-like.

    Takes in the tuple of the raw agent database results.
    """
    if not isinstance(agent, dict):
        agent_table = {}
        agent_table['checkin_time'] = str(agent.checkin_time)
        agent_table['delay'] = str(agent.delay)
        agent_table['external_ip'] = agent.external_ip
        agent_table['high_integrity'] = str(agent.high_integrity)
        agent_table['hostname'] = agent.hostname
        agent_table['internal_ip'] = agent.internal_ip
        agent_table['jitter'] = str(agent.jitter)
        agent_table['kill_date'] = agent.kill_date
        agent_table['language'] = agent.language
        agent_table['language_version'] = agent.language_version
        agent_table['lastseen_time'] = str(agent.lastseen_time)
        agent_table['listener'] = agent.listener
        agent_table['lost_limit'] = str(agent.lost_limit)
        agent_table['name'] = agent.name
        agent_table['nonce'] = agent.nonce
        agent_table['os_details'] = agent.os_details
        agent_table['process_id'] = str(agent.process_id)
        agent_table['process_name'] = agent.process_name
        agent_table['profile'] = agent.profile
        agent_table['session_id'] = agent.session_id
        agent_table['session_key'] = agent.session_key
        agent_table['username'] = agent.username
        agent_table['working_hours'] = agent.working_hours

    else:
        agent_table = agent

    if returnAsString:
        agentString = "\n[*] Agent info:\n"
        for key, value in agent_table.items():
            if key != 'functions' and key != 'takings' and key != 'results':
                agentString += "  %s\t%s\n" % ('{0: <16}'.format(key), wrap_string(value, width=70))
        return agentString + '\n'
    else:
        print(helpers.color("\n[*] Agent info:\n"))
        for key, value in agent_table.items():
            if key != 'functions' and key != 'takings' and key != 'results':
                print("\t%s\t%s" % (helpers.color('{0: <16}'.format(key), "blue"), wrap_string(value, width=70)))
        print('')


def display_listeners(listeners, type = "Active"):
    """
    Take an active listeners list and display everything nicely.
    """

    if len(listeners) > 0:
        print('')
        print(helpers.color("[*] %s listeners:\n" % type))

        name_len = max([len(name) for name in listeners.keys()]) + 2

        print(f"  Name{(name_len-4) * ' '}Module          Host                                 Delay/Jitter   KillDate")
        print(f"  ----{(name_len-4) * ' '}------          ----                                 ------------   --------")

        for listenerName, listener in listeners.items():

            moduleName = listener['moduleName']
            if 'Host' in listener['options']:
                host = listener['options']['Host']['Value']
            else:
                host = ''

            if 'DefaultDelay' in listener['options']:
                defaultDelay = listener['options']['DefaultDelay']['Value']
            else:
                defaultDelay = 'n/a'

            if 'DefaultJitter' in listener['options']:
                defaultJitter = listener['options']['DefaultJitter']['Value']
            else:
                defaultJitter = ''
            
            if defaultDelay == 'n/a':
                connectInterval = 'n/a'
            else:
                connectInterval = "%s/%s" % (defaultDelay, defaultJitter)

            if 'KillDate' in listener['options']:
                killDate = listener['options']['KillDate']['Value']
            else:
                killDate = 'n/a'

            print("  %s%s%s%s%s" % (f'{listenerName}{(name_len-len(listenerName)) * " "}', '{0: <16}'.format(moduleName), '{0: <37}'.format(host), '{0: <15}'.format(connectInterval), '{0: <12}'.format(killDate)))

        print('')

    else:
        if(type.lower() != "inactive"):
            print(helpers.color("[!] No listeners currently %s " % type.lower()))


def display_active_listener(listener):
    """
    Displays an active listener's information structure.
    """

    print("\n%s Options:\n" % (listener['options']['Name']['Value']))
    print("  Name              Required    Value                            Description")
    print("  ----              --------    -------                          -----------")

    for option, values in listener['options'].items():
        # if there's a long value length, wrap it
        if len(str(values['Value'])) > 33:
            print("  %s%s%s" % ('{0: <18}'.format(option), '{0: <12}'.format(("True" if values['Required'] else "False")), '{0: <33}'.format(wrap_string(values['Value'], width=32, indent=32, followingHeader=values['Description']))))
        else:
            print("  %s%s%s%s" % ('{0: <18}'.format(option), '{0: <12}'.format(("True" if values['Required'] else "False")), '{0: <33}'.format(values['Value']), values['Description']))

    print("\n")


def display_listener_module(listener):
    """
    Displays a listener module's information structure.
    """

    print('\n{0: >10}'.format("Name: ") + str(listener.info['Name']))
    print('{0: >10}'.format("Category: ") + str(listener.info['Category']))

    print("\nAuthors:")
    for author in listener.info['Author']:
        print("  " +author)

    print("\nDescription:")
    desc = wrap_string(listener.info['Description'], width=60, indent=2, indentAll=True)
    if len(desc.splitlines()) == 1:
        print("  " + str(desc))
    else:
        print(desc)

    if 'Comments' in listener.info:
        comments = listener.info['Comments']
        if isinstance(comments, list):
            comments = ' '.join(comments)
        if comments.strip() != '':
            print("\nComments:")
            if isinstance(comments, list):
                comments = ' '.join(comments)
            comment = wrap_string(comments, width=60, indent=2, indentAll=True)
            if len(comment.splitlines()) == 1:
                print("  " + str(comment))
            else:
                print(comment)


    print("\n%s Options:\n" % (listener.info['Name']))
    print("  Name              Required    Value                            Description")
    print("  ----              --------    -------                          -----------")

    for option, values in listener.options.items():
        # if there's a long value length, wrap it
        if len(str(values['Value'])) > 33:
            print("  %s%s%s" % ('{0: <18}'.format(option), '{0: <12}'.format(("True" if values['Required'] else "False")), '{0: <33}'.format(wrap_string(values['Value'], width=32, indent=32, followingHeader=values['Description']))))
        else:
            print("  %s%s%s%s" % ('{0: <18}'.format(option), '{0: <12}'.format(("True" if values['Required'] else "False")), '{0: <33}'.format(values['Value']), values['Description']))

    print("\n")


def display_stager(stager):
    """
    Displays a stager's information structure.
    """

    print("\nName: " + stager.info['Name'])

    print("\nDescription:")
    desc = wrap_string(stager.info['Description'], width=50, indent=2, indentAll=True)
    if len(desc.splitlines()) == 1:
        print("  " + str(desc))
    else:
        print(desc)

    # print out any options, if present
    if stager.options:
        print("\nOptions:\n")
        print("  Name             Required    Value             Description")
        print("  ----             --------    -------           -----------")

        for option, values in stager.options.items():
            print("  %s%s%s%s" % ('{0: <17}'.format(option), '{0: <12}'.format(("True" if values['Required'] else "False")), '{0: <18}'.format(values['Value']), wrap_string(values['Description'], indent=49)))

    print("\n")


def display_module(moduleName, module):
    """
    Displays a module's information structure.
    """

    print('\n{0: >20}'.format("Name: ") + str(module.info['Name']))
    print('{0: >20}'.format("Module: ") + str(moduleName))
    if 'NeedsAdmin' in module.info:
        print('{0: >20}'.format("NeedsAdmin: ") + ("True" if module.info['NeedsAdmin'] else "False"))
    if 'OpsecSafe' in module.info:
        print('{0: >20}'.format("OpsecSafe: ") + ("True" if module.info['OpsecSafe'] else "False"))
    if 'Language' in module.info:
        print('{0: >20}'.format("Language: ") + str(module.info['Language']))
    if 'MinLanguageVersion' in module.info:
        print('{0: >20}'.format("MinLanguageVersion: ") + str(module.info['MinLanguageVersion']))
    if 'Background' in module.info:
        print('{0: >20}'.format("Background: ") + ("True" if module.info['Background'] else "False"))
    if 'OutputExtension' in module.info:
        print('{0: >20}'.format("OutputExtension: ") + (str(module.info['OutputExtension']) if module.info['OutputExtension'] else "None"))

    print("\nAuthors:")
    for author in module.info['Author']:
        print("  " +author)

    print("\nDescription:")
    desc = wrap_string(module.info['Description'], width=60, indent=2, indentAll=True)
    if len(desc.splitlines()) == 1:
        print("  " + str(desc))
    else:
        print(desc)

    if 'Comments' in module.info:
        comments = module.info['Comments']
        if isinstance(comments, list):
            comments = ' '.join(comments)
        if comments.strip() != '':
            print("\nComments:")
            if isinstance(comments, list):
                comments = ' '.join(comments)
            comment = wrap_string(comments, width=60, indent=2, indentAll=True)
            if len(comment.splitlines()) == 1:
                print("  " + str(comment))
            else:
                print(comment)

    # print out any options, if present
    if module.options:

        # get the size for the first column
        maxNameLen = len(max(list(module.options.keys()), key=len))

        print("\nOptions:\n")
        print("  %sRequired    Value                     Description" %('{:<{}s}'.format("Name", maxNameLen+1)))
        print("  %s--------    -------                   -----------" %('{:<{}s}'.format("----", maxNameLen+1)))

        for option, values in module.options.items():
            print("  %s%s%s" % ('{:<{}s}'.format(str(option), maxNameLen+1), '{0: <12}'.format(("True" if values['Required'] else "False")), wrap_columns(str(values['Value']), str(values['Description']), indent=(31 + (maxNameLen-16)))))

    print('')


def display_module_search(moduleName, module):
    """
    Displays the name/description of a module for search results.
    """

    # Suffix modules requring elevated context with '*'
    if module.info['NeedsAdmin']:
        print(" %s*\n" % (helpers.color(moduleName, 'blue')))
    else:
        print(" %s\n" % (helpers.color(moduleName, 'blue')))
    # width=40, indent=32, indentAll=False,

    lines = textwrap.wrap(textwrap.dedent(module.info['Description']).strip(), width=70)
    for line in lines:
        print("\t" + line)

    print("\n")


def display_credentials(creds):
    """
    Take a credential array and display everything nicely.
    """

    print(helpers.color("\nCredentials:\n", "blue"))
    print("  CredID  CredType   Domain                   UserName         Host             Password")
    print("  ------  --------   ------                   --------         ----             --------")

    for cred in creds:
        # (id, credtype, domain, username, password, host, notes, sid)
        credID = cred['id']
        credType = cred['credtype']
        domain = cred['domain']
        username = cred['username']
        password = cred['password']
        if isinstance(cred['host'], bytes):
            host = cred['host'].decode('latin-1')
        else:
            host = cred['host']
        print("  %s%s%s%s%s%s" % ('{0: <8}'.format(credID), '{0: <11}'.format(credType), '{0: <25}'.format(domain), '{0: <17}'.format(username), '{0: <17}'.format(host), password))

    print('')
