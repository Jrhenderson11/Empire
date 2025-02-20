#!/usr/bin/env python3

from __future__ import print_function

import argparse
import base64
import copy
import hashlib
import json
import logging
import os
import pkgutil
import signal
import ssl
import string
import subprocess
import sys
import time
import random

from time import sleep
from datetime import datetime, timezone, date

import flask
from flask import Flask, request, jsonify, make_response, abort, url_for, g
from flask.json import JSONEncoder
from flask_socketio import SocketIO, emit, join_room, leave_room, \
    close_room, rooms, disconnect
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import aliased

# Empire imports
from lib import arguments
from lib.common import empire, helpers, users
from lib.common.empire import MainMenu
from lib.database.base import Session
from lib.database import models

# Check if running Python 3
if sys.version[0] == '2':
    print(helpers.color("[!] Please use Python 3"))
    sys.exit()

if os.geteuid() != 0:
    print(helpers.color("[!] Should be run as root"))
    sys.exit()

global serverExitCommand
serverExitCommand = 'restart'


#####################################################
#
# Database interaction methods for the RESTful API
#
#####################################################


def database_check_docker():
    """
    Check for docker and setup database if nessary.
    """
    if os.path.exists('/.dockerenv'):
        if not os.path.exists('data/empire.db'):
            print('[*] Fresh start in docker, running reset.sh for you')
            subprocess.call(['./setup/reset.sh'])


def adapt_datetime(val):
    """
    This adapter is available in sqlite3/dbapi2.py, but uses a " " as the seperator
    This uses the default of "T" which fits ISO-8601
    """
    return val.isoformat()


def convert_timestamp(val):
    """
    The original version of this in sqlite3/dbapi2.py doesn't account for timezone aware datetimes. Using fromisoformat
    should handle both naive and aware and astimezone will force naive timestamps to utc.
    datetimes.
    """
    return datetime.fromisoformat(val.decode('utf-8')).astimezone(timezone.utc)


class MyJsonEncoder(JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, bytes):
            return o.decode('latin-1')

        return super().default(o)

####################################################################
#
# The Empire RESTful API. To see more information about it, check out the official wiki.
#
# Adapted from http://blog.miguelgrinberg.com/post/designing-a-restful-api-with-python-and-flask.
# Example code at https://gist.github.com/miguelgrinberg/5614326.
#
#
#    Verb     URI                                                   Action
#    ----     ---                                                   ------
#    GET      http://localhost:1337/api/version                     return the current Empire version
#    GET      http://localhost:1337/api/map                         return list of all API routes
#    GET      http://localhost:1337/api/config                      return the current default config
#
#    GET      http://localhost:1337/api/stagers                     return all current stagers
#    GET      http://localhost:1337/api/stagers/X                   return the stager with name X
#    POST     http://localhost:1337/api/stagers                     generate a stager given supplied options (need to implement)
#
#    GET      http://localhost:1337/api/modules                     return all current modules
#    GET      http://localhost:1337/api/modules/<name>              return the module with the specified name
#    POST     http://localhost:1337/api/modules/<name>              execute the given module with the specified options
#    POST     http://localhost:1337/api/modules/search              searches modulesfor a passed term
#    POST     http://localhost:1337/api/modules/search/modulename   searches module names for a specific term
#    POST     http://localhost:1337/api/modules/search/description  searches module descriptions for a specific term
#    POST     http://localhost:1337/api/modules/search/comments     searches module comments for a specific term
#    POST     http://localhost:1337/api/modules/search/author       searches module authors for a specific term
#
#    GET      http://localhost:1337/api/listeners                   return all current listeners
#    GET      http://localhost:1337/api/listeners/Y                 return the listener with id Y
#    DELETE   http://localhost:1337/api/listeners/Y                 kills listener Y
#    GET      http://localhost:1337/api/listeners/types             returns a list of the loaded listeners that are available for use
#    GET      http://localhost:1337/api/listeners/options/Y         return listener options for Y
#    POST     http://localhost:1337/api/listeners/Y                 starts a new listener with the specified options
#
#    GET      http://localhost:1337/api/agents                      return all current agents
#    GET      http://localhost:1337/api/agents/stale                return all stale agents
#    DELETE   http://localhost:1337/api/agents/stale                removes stale agents from the database
#    DELETE   http://localhost:1337/api/agents/Y                    removes agent Y from the database
#    GET      http://localhost:1337/api/agents/Y                    return the agent with name Y
#    GET      http://localhost:1337/api/agents/Y/directory          return the directory with the name given by the query parameter 'directory'
#    POST     http://localhost:1337/api/agents/Y/directory          task the agent Y to scrape the directory given by the query parameter 'directory'
#    GET      http://localhost:1337/api/agents/Y/results            return tasking results for the agent with name Y
#    DELETE   http://localhost:1337/api/agents/Y/results            deletes the result buffer for agent Y
#    GET      http://localhost:1337/api/agents/Y/task/Z             return the tasking Z for agent Y
#    POST     http://localhost:1337/api/agents/Y/download           task agent Y to download a file
#    POST     http://localhost:1337/api/agents/Y/upload             task agent Y to upload a file
#    POST     http://localhost:1337/api/agents/Y/shell              task agent Y to execute a shell command
#    POST     http://localhost:1337/api/agents/Y/rename             rename agent Y
#    GET/POST http://localhost:1337/api/agents/Y/clear              clears the result buffer for agent Y
#    GET/POST http://localhost:1337/api/agents/Y/kill               kill agent Y
#
#    GET      http://localhost:1337/api/creds                       return stored credentials
#    POST     http://localhost:1337/api/creds                       add creds to the database
#
#    GET      http://localhost:1337/api/reporting                   return all logged events
#    GET      http://localhost:1337/api/reporting/agent/X           return all logged events for the given agent name X
#    GET      http://localhost:1337/api/reporting/type/Y            return all logged events of type Y (checkin, task, result, rename)
#    GET      http://localhost:1337/api/reporting/msg/Z             return all logged events matching message Z, wildcards accepted
#
#
#    POST     http://localhost:1337/api/admin/login                 retrieve the API token given the correct username and password
#    POST     http://localhost:1337/api/admin/logout                logout of current user account
#    GET      http://localhost:1337/api/admin/restart               restart the RESTful API
#    GET      http://localhost:1337/api/admin/shutdown              shutdown the RESTful API
#
#    GET      http://localhost:1337/api/users                       return all users from database
#    GET      http://localhost:1337/api/users/X                     return the user with id X
#    GET      http://localhost:1337/api/users/me                    return the user for the given token
#    POST     http://localhost:1337/api/users                       add a new user
#    PUT      http://localhost:1337/api/users/Y/disable             disable/enable user Y
#    PUT      http://localhost:1337/api/users/Y/updatepassword      update password for user Y
#
####################################################################

def start_restful_api(empireMenu: MainMenu, suppress=False, headless=False, username=None, password=None, port=1337):
    """
    Kick off the RESTful API with the given parameters.

    empireMenu  -   Main empire menu object
    suppress    -   suppress most console output
    username    -   optional username to use for the API, otherwise pulls from the empire.db config
    password    -   optional password to use for the API, otherwise pulls from the empire.db config
    port        -   port to start the API on, defaults to 1337 ;)
    """
    app = Flask(__name__)

    app.json_encoder = MyJsonEncoder

    main = empireMenu

    global serverExitCommand

    if username:
        main.users.update_username(1, username[0])

    if password:
        main.users.update_password(1, password[0])

    print('')
    print(" * Starting Empire RESTful API on port: %s" % (port))

    oldStdout = sys.stdout
    if suppress:
        # suppress the normal Flask output
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

    if headless:
        # suppress all stdout and don't initiate the main cmdloop
        sys.stdout = open(os.devnull, 'w')

    # validate API token before every request except for the login URI
    @app.before_request
    def check_token():
        """
        Before every request, check if a valid token is passed along with the request.
        """
        try:
            if request.path != '/api/admin/login':
                token = request.args.get('token')
                if token and len(token) > 0:
                    user = main.users.get_user_from_token(token)
                    if user:
                        g.user = user
                    else:
                        return make_response('', 401)
                else:
                    return make_response('', 401)
        except:
            return make_response('', 401)

    @app.after_request
    def add_cors(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response

    @app.teardown_request
    def remove_session(ex):
        Session.remove()

    @app.errorhandler(Exception)
    def exception_handler(error):
        """
        Generic exception handler.
        """
        code = error.code if hasattr(error, 'code') else '500'
        return make_response(jsonify({'error': repr(error)}), code)

    @app.errorhandler(404)
    def not_found(error):
        """
        404/not found handler.
        """
        return make_response(jsonify({'error': 'Not found'}), 404)

    @app.route('/api/version', methods=['GET'])
    def get_version():
        """
        Returns the current Empire version.
        """
        return jsonify({'version': empire.VERSION})

    @app.route('/api/map', methods=['GET'])
    def list_routes():
        """
        List all of the current registered API routes.
        """
        output = {}
        for rule in app.url_map.iter_rules():
            methods = ','.join(rule.methods)
            url = rule.rule
            output.update({rule.endpoint: {'methods': methods, 'url': url}})

        return jsonify({'Routes': output})

    @app.route('/api/config', methods=['GET'])
    def get_config():
        """
        Returns JSON of the current Empire config.
        """
        api_username = g.user['username']
        api_current_token = g.user['api_token']

        config = Session().query(models.Config).first()
        dictret = dict(config.__dict__);

        dictret.pop('_sa_instance_state', None)
        dictret['api_username'] = api_username
        dictret['current_api_token'] = api_current_token
        dictret['version'] = empire.VERSION

        return jsonify({"config": dictret})

    @app.route('/api/stagers', methods=['GET'])
    def get_stagers():
        """
        Returns JSON describing all stagers.
        """

        stagers = []
        for stagerName, stager in main.stagers.stagers.items():
            info = copy.deepcopy(stager.info)
            info['options'] = stager.options
            info['Name'] = stagerName
            stagers.append(info)

        return jsonify({'stagers': stagers})

    @app.route('/api/stagers/<path:stager_name>', methods=['GET'])
    def get_stagers_name(stager_name):
        """
        Returns JSON describing the specified stager_name passed.
        """
        if stager_name not in main.stagers.stagers:
            return make_response(jsonify({
                                             'error': 'stager name %s not found, make sure to use [os]/[name] format, ie. windows/dll' % (
                                                 stager_name)}), 404)

        stagers = []
        for stagerName, stager in main.stagers.stagers.items():
            if stagerName == stager_name:
                info = copy.deepcopy(stager.info)
                info['options'] = stager.options
                info['Name'] = stagerName
                stagers.append(info)

        return jsonify({'stagers': stagers})

    @app.route('/api/stagers', methods=['POST'])
    def generate_stager():
        """
        Generates a stager with the supplied config and returns JSON information
        describing the generated stager, with 'Output' being the stager output.

        Required JSON args:
            StagerName      -   the stager name to generate
            Listener        -   the Listener name to use for the stager
        """
        if not request.json or not 'StagerName' in request.json or not 'Listener' in request.json:
            abort(400)

        stagerName = request.json['StagerName']
        listener = request.json['Listener']

        if stagerName not in main.stagers.stagers:
            return make_response(jsonify({'error': 'stager name %s not found' % (stagerName)}), 404)

        if not main.listeners.is_listener_valid(listener):
            return make_response(jsonify({'error': 'invalid listener ID or name'}), 400)

        stager = main.stagers.stagers[stagerName]

        # set all passed options
        for option, values in request.json.items():
            if option != 'StagerName':
                if option not in stager.options:
                    return make_response(jsonify({'error': 'Invalid option %s, check capitalization.' % (option)}), 400)
                stager.options[option]['Value'] = values

        # validate stager options
        for option, values in stager.options.items():
            if values['Required'] and ((not values['Value']) or (values['Value'] == '')):
                return make_response(jsonify({'error': 'required stager options missing'}), 400)

        stagerOut = copy.deepcopy(stager.options)

        if ('OutFile' in stagerOut) and (stagerOut['OutFile']['Value'] != ''):
            if isinstance(stager.generate(), str):
                # if the output was intended for a file, return the base64 encoded text
                stagerOut['Output'] = base64.b64encode(stager.generate().encode('UTF-8'))
            else:
                stagerOut['Output'] = base64.b64encode(stager.generate())

        else:
            # otherwise return the text of the stager generation
            stagerOut['Output'] = stager.generate()

        return jsonify({stagerName: stagerOut})

    @app.route('/api/modules', methods=['GET'])
    def get_modules():
        """
        Returns JSON describing all currently loaded modules.
        """

        modules = []
        for moduleName, module in main.modules.modules.items():
            moduleInfo = copy.deepcopy(module.info)
            moduleInfo['options'] = module.options
            moduleInfo['Name'] = moduleName
            modules.append(moduleInfo)

        return jsonify({'modules': modules})

    @app.route('/api/modules/<path:module_name>', methods=['GET'])
    def get_module_name(module_name):
        """
        Returns JSON describing the specified currently module.
        """

        if module_name not in main.modules.modules:
            return make_response(jsonify({'error': 'module name %s not found' % (module_name)}), 404)

        modules = []
        moduleInfo = copy.deepcopy(main.modules.modules[module_name].info)
        moduleInfo['options'] = main.modules.modules[module_name].options
        moduleInfo['Name'] = module_name
        modules.append(moduleInfo)

        return jsonify({'modules': modules})

    @app.route('/api/modules/<path:module_name>', methods=['POST'])
    def execute_module(module_name):
        """
        Executes a given module name with the specified parameters.
        """

        # ensure the 'Agent' argument is set
        if not request.json or not 'Agent' in request.json:
            abort(400)

        if module_name not in main.modules.modules:
            return make_response(jsonify({'error': 'module name %s not found' % (module_name)}), 404)

        module = main.modules.modules[module_name]

        # set all passed module options
        for key, value in request.json.items():
            if key not in module.options:
                return make_response(jsonify({'error': 'invalid module option'}), 400)

            module.options[key]['Value'] = value

        # validate module options
        sessionID = module.options['Agent']['Value']

        for option, values in module.options.items():
            if values['Required'] and ((not values['Value']) or (values['Value'] == '')):
                return make_response(jsonify({'error': 'required module option missing'}), 400)

        try:
            # if we're running this module for all agents, skip this validation
            if sessionID.lower() != "all" and sessionID.lower() != "autorun":

                if not main.agents.is_agent_present(sessionID):
                    return make_response(jsonify({'error': 'invalid agent name'}), 400)

                moduleVersion = float(module.info['MinLanguageVersion'])
                agentVersion = float(main.agents.get_language_version_db(sessionID))
                # check if the agent/module PowerShell versions are compatible
                if moduleVersion > agentVersion:
                    return make_response(jsonify({'error': "module requires PS version " + str(
                        moduleVersion) + " but agent running PS version " + str(agentVersion)}), 400)

        except Exception as e:
            return make_response(jsonify({'error': 'exception: %s' % (e)}), 400)

        # check if the module needs admin privs
        if module.info['NeedsAdmin']:
            # if we're running this module for all agents, skip this validation
            if sessionID.lower() != "all" and sessionID.lower() != "autorun":
                if not main.agents.is_agent_elevated(sessionID):
                    return make_response(jsonify({'error': 'module needs to run in an elevated context'}), 400)

        # actually execute the module
        moduleData = module.generate()

        if not moduleData or moduleData == "":
            return make_response(jsonify({'error': 'module produced an empty script'}), 400)

        try:
            if isinstance(moduleData, bytes):
                moduleData = moduleData.decode('ascii')
        except UnicodeDecodeError:
            return make_response(jsonify({'error': 'module source contains non-ascii characters'}), 400)

        moduleData = helpers.strip_powershell_comments(moduleData)
        taskCommand = ""

        # build the appropriate task command and module data blob
        if str(module.info['Background']).lower() == "true":
            # if this module should be run in the background
            extention = module.info['OutputExtension']
            if extention and extention != "":
                # if this module needs to save its file output to the server
                #   format- [15 chars of prefix][5 chars extension][data]
                saveFilePrefix = module_name.split("/")[-1]
                moduleData = saveFilePrefix.rjust(15) + extention.rjust(5) + moduleData
                taskCommand = "TASK_CMD_JOB_SAVE"
            else:
                taskCommand = "TASK_CMD_JOB"

        else:
            # if this module is run in the foreground
            extention = module.info['OutputExtension']
            if module.info['OutputExtension'] and module.info['OutputExtension'] != "":
                # if this module needs to save its file output to the server
                #   format- [15 chars of prefix][5 chars extension][data]
                saveFilePrefix = module_name.split("/")[-1][:15]
                moduleData = saveFilePrefix.rjust(15) + extention.rjust(5) + moduleData
                taskCommand = "TASK_CMD_WAIT_SAVE"
            else:
                taskCommand = "TASK_CMD_WAIT"

        if sessionID.lower() == "all":

            for agent in main.agents.get_agents():
                sessionID = agent[1]
                taskID = main.agents.add_agent_task_db(sessionID, taskCommand, moduleData, moduleName=module_name,
                                                       uid=g.user['id'])
                msg = "tasked agent %s to run module %s" % (sessionID, module_name)
                main.agents.save_agent_log(sessionID, msg)

            msg = "tasked all agents to run module %s" % (module_name)
            return jsonify({'success': True, 'taskID': taskID, 'msg': msg})

        else:
            # set the agent's tasking in the cache
            taskID = main.agents.add_agent_task_db(sessionID, taskCommand, moduleData, moduleName=module_name,
                                                   uid=g.user['id'])

            # update the agent log
            msg = "tasked agent %s to run module %s" % (sessionID, module_name)
            main.agents.save_agent_log(sessionID, msg)
            return jsonify({'success': True, 'taskID': taskID, 'msg': msg})

    @app.route('/api/modules/search', methods=['POST'])
    def search_modules():
        """
        Returns JSON describing the the modules matching the passed
        'term' search parameter. Module name, description, comments,
        and author fields are searched.
        """

        if not request.json or not 'term':
            abort(400)

        searchTerm = request.json['term']

        modules = []

        for moduleName, module in main.modules.modules.items():
            if (searchTerm.lower() == '') or (searchTerm.lower() in moduleName.lower()) or (
                    searchTerm.lower() in ("".join(module.info['Description'])).lower()) or (
                    searchTerm.lower() in ("".join(module.info['Comments'])).lower()) or (
                    searchTerm.lower() in ("".join(module.info['Author'])).lower()):
                moduleInfo = copy.deepcopy(main.modules.modules[moduleName].info)
                moduleInfo['options'] = main.modules.modules[moduleName].options
                moduleInfo['Name'] = moduleName
                modules.append(moduleInfo)

        return jsonify({'modules': modules})

    @app.route('/api/modules/search/modulename', methods=['POST'])
    def search_modules_name():
        """
        Returns JSON describing the the modules matching the passed
        'term' search parameter for the modfule name.
        """

        if not request.json or not 'term':
            abort(400)

        searchTerm = request.json['term']

        modules = []

        for moduleName, module in main.modules.modules.items():
            if (searchTerm.lower() == '') or (searchTerm.lower() in moduleName.lower()):
                moduleInfo = copy.deepcopy(main.modules.modules[moduleName].info)
                moduleInfo['options'] = main.modules.modules[moduleName].options
                moduleInfo['Name'] = moduleName
                modules.append(moduleInfo)

        return jsonify({'modules': modules})

    @app.route('/api/modules/search/description', methods=['POST'])
    def search_modules_description():
        """
        Returns JSON describing the the modules matching the passed
        'term' search parameter for the 'Description' field.
        """

        if not request.json or not 'term':
            abort(400)

        searchTerm = request.json['term']

        modules = []

        for moduleName, module in main.modules.modules.items():
            if (searchTerm.lower() == '') or (searchTerm.lower() in ("".join(module.info['Description'])).lower()):
                moduleInfo = copy.deepcopy(main.modules.modules[moduleName].info)
                moduleInfo['options'] = main.modules.modules[moduleName].options
                moduleInfo['Name'] = moduleName
                modules.append(moduleInfo)

        return jsonify({'modules': modules})

    @app.route('/api/modules/search/comments', methods=['POST'])
    def search_modules_comments():
        """
        Returns JSON describing the the modules matching the passed
        'term' search parameter for the 'Comments' field.
        """

        if not request.json or not 'term':
            abort(400)

        searchTerm = request.json['term']

        modules = []

        for moduleName, module in main.modules.modules.items():
            if (searchTerm.lower() == '') or (searchTerm.lower() in ("".join(module.info['Comments'])).lower()):
                moduleInfo = copy.deepcopy(main.modules.modules[moduleName].info)
                moduleInfo['options'] = main.modules.modules[moduleName].options
                moduleInfo['Name'] = moduleName
                modules.append(moduleInfo)

        return jsonify({'modules': modules})

    @app.route('/api/modules/search/author', methods=['POST'])
    def search_modules_author():
        """
        Returns JSON describing the the modules matching the passed
        'term' search parameter for the 'Author' field.
        """

        if not request.json or not 'term':
            abort(400)

        searchTerm = request.json['term']

        modules = []

        for moduleName, module in main.modules.modules.items():
            if (searchTerm.lower() == '') or (searchTerm.lower() in ("".join(module.info['Author'])).lower()):
                moduleInfo = copy.deepcopy(main.modules.modules[moduleName].info)
                moduleInfo['options'] = main.modules.modules[moduleName].options
                moduleInfo['Name'] = moduleName
                modules.append(moduleInfo)

        return jsonify({'modules': modules})

    @app.route('/api/listeners', methods=['GET'])
    def get_listeners():
        """
        Returns JSON describing all currently registered listeners.
        """
        active_listeners_raw = Session().query(models.Listener).all()

        listeners = []
        for active_listener in active_listeners_raw:
            listeners.append({'ID': active_listener.id, 'name': active_listener.name, 'module': active_listener.module,
                              'listener_type': active_listener.listener_type,
                              'listener_category': active_listener.listener_category,
                              'options': active_listener.options,
                              'created_at': active_listener.created_at})

        return jsonify({"listeners": listeners})

    @app.route('/api/listeners/<string:listener_name>', methods=['GET'])
    def get_listener_name(listener_name):
        """
        Returns JSON describing the listener specified by listener_name.
        """
        active_listener = Session().query(models.Listener).filter(models.Listener.name == listener_name).first()

        listeners = []
        if active_listener.name == listener_name:
            listeners.append({'ID': active_listener.id, 'name': active_listener.name, 'module': active_listener.module,
                              'listener_type': active_listener.listener_type,
                              'listener_category': active_listener.listener_category,
                              'options': active_listener.options})
            return jsonify({'listeners': listeners})
        else:
            return make_response(jsonify({'error': 'listener name %s not found' % (listener_name)}), 404)

    @app.route('/api/listeners/<string:listener_name>', methods=['DELETE'])
    def kill_listener(listener_name):
        """
        Kills the listener specified by listener_name.
        """
        if listener_name.lower() == "all":
            active_listeners_raw = Session().query(models.Listener).all()
            for active_listener in active_listeners_raw:
                main.listeners.kill_listener(active_listener.name)

            return jsonify({'success': True})
        else:
            if listener_name != "" and main.listeners.is_listener_valid(listener_name):
                main.listeners.kill_listener(listener_name)
                return jsonify({'success': True})
            else:
                return make_response(jsonify({'error': 'listener name %s not found' % (listener_name)}), 404)

    @app.route('/api/listeners/types', methods=['GET'])
    def get_listener_types():
        """
        Returns a list of the loaded listeners that are available for use.
        """

        return jsonify({'types': list(main.listeners.loadedListeners.keys())})

    @app.route('/api/listeners/options/<string:listener_type>', methods=['GET'])
    def get_listener_options(listener_type):
        """
        Returns JSON describing listener options for the specified listener type.
        """

        if listener_type.lower() not in main.listeners.loadedListeners:
            return make_response(jsonify({'error': 'listener type %s not found' % (listener_type)}), 404)

        options = main.listeners.loadedListeners[listener_type].options
        return jsonify({'listeneroptions': options})

    @app.route('/api/listeners/<string:listener_type>', methods=['POST'])
    def start_listener(listener_type):
        """
        Starts a listener with options supplied in the POST.
        """
        if listener_type.lower() not in main.listeners.loadedListeners:
            return make_response(jsonify({'error': 'listener type %s not found' % (listener_type)}), 404)

        listenerObject = main.listeners.loadedListeners[listener_type]
        # set all passed options
        for option, values in request.json.items():
            if isinstance(values, bytes):
                values = values.decode('UTF-8')
            if option == "Name":
                listenerName = values

            returnVal = main.listeners.set_listener_option(listener_type, option, values)
            if not returnVal:
                return make_response(
                    jsonify({'error': 'error setting listener value %s with option %s' % (option, values)}), 400)

        main.listeners.start_listener(listener_type, listenerObject)

        # check to see if the listener was created
        listenerID = main.listeners.get_listener_id(listenerName)
        if listenerID:
            return jsonify({'success': 'Listener %s successfully started' % listenerName})
        else:
            return jsonify({'error': 'failed to start listener %s' % listenerName})

    @app.route('/api/agents', methods=['GET'])
    def get_agents():
        """
        Returns JSON describing all currently registered agents.
        """
        active_agents_raw = Session().query(models.Agent).all()
        agents = []

        for active_agent in active_agents_raw:
            agents.append(
                {"ID": active_agent.id, "session_id": active_agent.session_id, "listener": active_agent.listener,
                 "name": active_agent.name, "language": active_agent.language,
                 "language_version": active_agent.language_version, "delay": active_agent.delay,
                 "jitter": active_agent.jitter, "external_ip": active_agent.external_ip,
                 "internal_ip": active_agent.internal_ip, "username": active_agent.username,
                 "high_integrity": int(active_agent.high_integrity or 0), "process_name": active_agent.process_name,
                 "process_id": active_agent.process_id, "hostname": active_agent.hostname,
                 "os_details": active_agent.os_details,
                 "session_key": str(active_agent.session_key),
                 "nonce": active_agent.nonce, "checkin_time": active_agent.checkin_time,
                 "lastseen_time": active_agent.lastseen_time, "parent": active_agent.parent,
                 "children": active_agent.children, "servers": active_agent.servers, "profile": active_agent.profile,
                 "functions": active_agent.functions, "kill_date": active_agent.kill_date,
                 "working_hours": active_agent.working_hours, "lost_limit": active_agent.lost_limit,
                 "taskings": active_agent.taskings, "results": active_agent.results, "stale": active_agent.stale,
                 "notes": active_agent.notes})

        return jsonify({'agents': agents})

    @app.route('/api/agents/stale', methods=['GET'])
    def get_agents_stale():
        """
        Returns JSON describing all stale agents.
        """

        agents_raw = Session().query(models.Agent).all()
        stale_agents = []

        for agent in agents_raw:
            if agent.stale:
                stale_agents.append(
                    {"ID": agent.id, "session_id": agent.session_id, "listener": agent.listener, "name": agent.name,
                     "language": agent.language, "language_version": agent.language_version, "delay": agent.delay,
                     "jitter": agent.jitter, "external_ip": agent.external_ip, "internal_ip": agent.internal_ip,
                     "username": agent.username, "high_integrity": int(agent.high_integrity or 0),
                     "process_name": agent.process_name, "process_id": agent.process_id, "hostname": agent.hostname,
                     "os_details": agent.os_details, "session_key": str(agent.session_key), "nonce": agent.nonce,
                     "checkin_time": agent.checkin_time, "lastseen_time": agent.lastseen_time, "parent": agent.parent,
                     "children": agent.children, "servers": agent.servers, "profile": agent.profile,
                     "functions": agent.functions, "kill_date": agent.kill_date, "working_hours": agent.working_hours,
                     "lost_limit": agent.lost_limit, "taskings": agent.taskings, "results": agent.results})

        return jsonify({'agents': stale_agents})

    @app.route('/api/agents/stale', methods=['DELETE'])
    def remove_stale_agent():
        """
        Removes stale agents from the controller.

        WARNING: doesn't kill the agent first! Ensure the agent is dead.
        """
        agents_raw = Session().query(models.Agent).all()

        for agent in agents_raw:

            if agent.stale:
                Session().delete(agent)
        Session().commit()

        return jsonify({'success': True})

    @app.route('/api/agents/<string:agent_name>', methods=['DELETE'])
    def remove_agent(agent_name):
        """
        Removes an agent from the controller specified by agent_name.

        WARNING: doesn't kill the agent first! Ensure the agent is dead.
        """
        agent = main.agents.get_agent_from_name_or_session_id(agent_name)

        if not agent:
            return make_response(jsonify({'error': 'agent name %s not found' % (agent_name)}), 404)

        Session().delete(agent)
        Session().commit()

        return jsonify({'success': True})

    @app.route('/api/agents/<string:agent_name>', methods=['GET'])
    def get_agents_name(agent_name):
        """
        Returns JSON describing the agent specified by agent_name.
        """
        agent = Session().query(models.Agent).filter(models.Agent.name == agent_name).first()
        active_agent = []
        active_agent.append(
            {"ID": agent.id, "session_id": agent.session_id, "listener": agent.listener, "name": agent.name,
             "language": agent.language, "language_version": agent.language_version, "delay": agent.delay,
             "jitter": agent.jitter, "external_ip": agent.external_ip, "internal_ip": agent.internal_ip,
             "username": agent.username, "high_integrity": int(agent.high_integrity or 0),
             "process_name": agent.process_name,
             "process_id": agent.process_id, "hostname": agent.hostname, "os_details": agent.os_details,
             "session_key": str(agent.session_key),
             "nonce": agent.nonce, "checkin_time": agent.checkin_time,
             "lastseen_time": agent.lastseen_time, "parent": agent.parent, "children": agent.children,
             "servers": agent.servers, "profile": agent.profile, "functions": agent.functions,
             "kill_date": agent.kill_date, "working_hours": agent.working_hours,
             "lost_limit": agent.lost_limit,
             "taskings": agent.taskings, "results": agent.results})

        return jsonify({'agents': active_agent})

    @app.route('/api/agents/<string:agent_name>/directory', methods=['POST'])
    def scrape_agent_directory(agent_name):
        directory = '/' if request.args.get('directory') is None else request.args.get('directory')
        task_id = main.agents.add_agent_task_db(agent_name, "TASK_DIR_LIST", directory, g.user['id'])
        return jsonify({'taskID': task_id})

    @app.route('/api/agents/<string:agent_name>/directory', methods=['GET'])
    def get_agent_directory(agent_name):
        # Would be cool to add a "depth" param
        directory = '/' if request.args.get('directory') is None else request.args.get('directory')

        found = Session().query(models.AgentFile).filter(and_(
            models.AgentFile.session_id == agent_name,
            models.AgentFile.path == directory)).first()

        if not found:
            return make_response(jsonify({'error': "Directory not found."}), 404)

        agent_file_alias = aliased(models.AgentFile)
        results = Session() \
            .query(models.AgentFile.id.label("id"),
                   models.AgentFile.session_id.label("session_id"),
                   models.AgentFile.name.label("name"),
                   models.AgentFile.path.label("path"),
                   models.AgentFile.parent_id.label("parent_id"),
                   models.AgentFile.is_file.label("is_file"),
                   agent_file_alias.name.label("parent_name"),
                   agent_file_alias.path.label("parent_path"),
                   agent_file_alias.parent_id.label("parent_parent")) \
            .select_from(models.AgentFile) \
            .join(agent_file_alias,
                  models.AgentFile.parent_id == agent_file_alias.id) \
            .filter(and_(models.AgentFile.session_id == agent_name, agent_file_alias.path == directory)) \
            .all()

        response = []
        for result in results:
            response.append({'id': result.id, 'session_id': result.session_id, 'name': result.name, 'path': result.path,
                             'parent_id': result.parent_id, 'is_file': result.is_file, 'parent_name': result.parent_name,
                             'parent_path': result.parent_path, 'parent_parent': result.parent_parent})

        return jsonify({'items': response})

    @app.route('/api/agents/<string:agent_name>/results', methods=['GET'])
    def get_agent_results(agent_name):
        """
        Returns JSON describing the agent's results and removes the result field
        from the backend database.
        """
        agent_task_results = []

        agent_results_raw = Session() \
            .query(models.Result.id.label("task_id"),
                   models.Tasking.data.label("command"),
                   models.Result.data.label("result"),
                   models.User.id.label("user_id"),
                   models.User.username.label("username")) \
            .select_from(models.Result) \
            .join(models.Tasking,
                  and_(models.Tasking.id == models.Result.id, models.Tasking.agent == models.Result.agent)) \
            .outerjoin(models.User, models.Tasking.user_id == models.User.id) \
            .filter(models.Result.agent == agent_name) \
            .all()

        results = []
        for agent_results in agent_results_raw:
            if len(agent_results) > 0:
                results.append(
                    {'taskID': agent_results.task_id, 'command': agent_results.command, 'results': agent_results.result,
                     'user_id': agent_results.user_id,
                     'username': agent_results.username})

        agent_task_results.append({"AgentName": agent_name, "AgentResults": results})

        return jsonify({'results': agent_task_results})

    @app.route('/api/agents/<string:agent_name>/task/<int:task_id>', methods=['GET'])
    def get_task(agent_name, task_id):
        agent_results = Session() \
            .query(models.Result.id.label("task_id"),
                   models.Tasking.data.label("command"),
                   models.Result.data.label("result"),
                   models.User.id.label("user_id"),
                   models.User.username.label("username")) \
            .select_from(models.Result) \
            .join(models.Tasking,
                  and_(task_id == models.Result.id, agent_name == models.Result.agent)) \
            .outerjoin(models.User, models.Tasking.user_id == models.User.id) \
            .filter(models.Result.agent == agent_name) \
            .first()

        if agent_results:
            return make_response(jsonify(
                {'taskID': agent_results.task_id, 'command': agent_results.command, 'results': agent_results.result,
                 'user_id': agent_results.user_id, 'username': agent_results.username}))

        return make_response(jsonify({'error': 'task not found.'}), 404)

    @app.route('/api/agents/<string:agent_name>/results', methods=['DELETE'])
    def delete_agent_results(agent_name):
        """
        Removes the specified agent results field from the backend database.
        """
        agent = main.agents.get_agent_from_name_or_session_id(agent_name)

        if not agent:
            return make_response(jsonify({'error': 'agent name %s not found' % (agent_name)}), 404)

        agent.results = ''
        Session().commit()

        return jsonify({'success': True})

    @app.route('/api/agents/<string:agent_name>/download', methods=['POST'])
    def task_agent_download(agent_name):
        """
        Tasks the specified agent to download a file
        """
        agent = main.agents.get_agent_from_name_or_session_id(agent_name)

        if agent is None:
            return make_response(jsonify({'error': 'agent name %s not found' % agent_name}), 404)

        if not request.json['filename']:
            return make_response(jsonify({'error': 'file name not provided'}), 404)

        file_name = request.json['filename']

        msg = "Tasked agent to download %s" % file_name
        main.agents.save_agent_log(agent.session_id, msg)
        task_id = main.agents.add_agent_task_db(agent.session_id, 'TASK_DOWNLOAD', file_name, uid=g.user['id'])

        return jsonify({'success': True, 'taskID': task_id})

    @app.route('/api/agents/<string:agent_name>/upload', methods=['POST'])
    def task_agent_upload(agent_name):
        """
        Tasks the specified agent to upload a file
        """
        agent = main.agents.get_agent_from_name_or_session_id(agent_name)

        if agent is None:
            return make_response(jsonify({'error': 'agent name %s not found' % (agent_name)}), 404)

        if not request.json['data']:
            return make_response(jsonify({'error': 'file data not provided'}), 404)

        if not request.json['filename']:
            return make_response(jsonify({'error': 'file name not provided'}), 404)

        file_data = request.json['data']
        file_name = request.json['filename']

        raw_bytes = base64.b64decode(file_data)

        if len(raw_bytes) > 1048576:
            return make_response(jsonify({'error': 'file size too large'}), 404)

        msg = "Tasked agent to upload %s : %s" % (file_name, hashlib.md5(raw_bytes).hexdigest())
        main.agents.save_agent_log(agent.session_id, msg)
        data = file_name + "|" + file_data
        task_id = main.agents.add_agent_task_db(agent.session_id, 'TASK_UPLOAD', data, uid=g.user['id'])

        return jsonify({'success': True, 'taskID': task_id})

    @app.route('/api/agents/<string:agent_name>/shell', methods=['POST'])
    def task_agent_shell(agent_name):
        """
        Tasks an the specified agent_name to execute a shell command.

        Takes {'command':'shell_command'}
        """
        agent = main.agents.get_agent_from_name_or_session_id(agent_name)

        if agent is None:
            return make_response(jsonify({'error': 'agent name %s not found' % (agent_name)}), 404)

        command = request.json['command']

        # add task command to agent taskings
        msg = "tasked agent %s to run command %s" % (agent.session_id, command)
        main.agents.save_agent_log(agent.session_id, msg)
        task_id = main.agents.add_agent_task_db(agent.session_id, "TASK_SHELL", command, uid=g.user['id'])

        return jsonify({'success': True, 'taskID': task_id})

    @app.route('/api/agents/<string:agent_name>/update_comms', methods=['PUT'])
    def agent_update_comms(agent_name):
        """
        Dynamically update the agent comms to another

        Takes {'listener': 'name'}
        """

        if not request.json:
            return make_response(jsonify({'error': 'request body must be valid JSON'}), 400)

        if not 'listener' in request.json:
            return make_response(jsonify({'error': 'JSON body must include key "listener"'}), 400)

        listener_name = request.json['listener']

        if not main.listeners.is_listener_valid(listener_name):
            return jsonify({'error': 'Please enter a valid listener name.'})
        else:
            active_listener = main.listeners.activeListeners[listener_name]
            if active_listener['moduleName'] != 'meterpreter' or active_listener['moduleName'] != 'http_mapi':
                listener_options = active_listener['options']
                listener_comms = main.listeners.loadedListeners[active_listener['moduleName']].generate_comms(
                    listener_options, language="powershell")

                main.agents.add_agent_task_db(agent_name, "TASK_UPDATE_LISTENERNAME", listener_options['Name']['Value'])
                main.agents.add_agent_task_db(agent_name, "TASK_SWITCH_LISTENER", listener_comms)

                msg = "Tasked agent to update comms to %s listener" % listener_name
                main.agents.save_agent_log(agent_name, msg)
                return jsonify({'success': True})
            else:
                return jsonify(
                    {'error': 'Ineligible listener for updatecomms command: %s' % active_listener['moduleName']})

    @app.route('/api/agents/<string:agent_name>/killdate', methods=['PUT'])
    def agent_kill_date(agent_name):
        """
        Set an agent's killdate (01/01/2016)

        Takes {'kill_date': 'date'}
        """

        if not request.json:
            return make_response(jsonify({'error': 'request body must be valid JSON'}), 400)

        if not 'kill_date' in request.json:
            return make_response(jsonify({'error': 'JSON body must include key "kill_date"'}), 400)

        try:
            kill_date = request.json['kill_date']

            # update this agent's information in the database
            main.agents.set_agent_field_db("kill_date", kill_date, agent_name)

            # task the agent
            main.agents.add_agent_task_db(agent_name, "TASK_SHELL", "Set-KillDate " + str(kill_date))

            # update the agent log
            msg = "Tasked agent to set killdate to " + str(kill_date)
            main.agents.save_agent_log(agent_name, msg)
            return jsonify({'success': True})
        except:
            return jsonify({'error': 'Unable to update agent killdate'})

    @app.route('/api/agents/<string:agent_name>/workinghours', methods=['PUT'])
    def agent_working_hours(agent_name):
        """
        Set an agent's working hours (9:00-17:00)

        Takes {'working_hours': 'working_hours'}
        """

        if not request.json:
            return make_response(jsonify({'error': 'request body must be valid JSON'}), 400)

        if not 'working_hours' in request.json:
            return make_response(jsonify({'error': 'JSON body must include key "working_hours"'}), 400)

        try:
            working_hours = request.json['working_hours']
            working_hours = working_hours.replace(",", "-")

            # update this agent's information in the database
            main.agents.set_agent_field_db("working_hours", working_hours, agent_name)

            # task the agent
            main.agents.add_agent_task_db(agent_name, "TASK_SHELL", "Set-WorkingHours " + str(working_hours))

            # update the agent log
            msg = "Tasked agent to set working hours to " + str(working_hours)
            main.agents.save_agent_log(agent_name, msg)
            return jsonify({'success': True})
        except:
            return jsonify({'error': 'Unable to update agent workinghours'})

    @app.route('/api/agents/<string:agent_name>/rename', methods=['POST'])
    def task_agent_rename(agent_name):
        """
        Renames the specified agent.

        Takes {'newname': 'NAME'}
        """

        agent = main.agents.get_agent_from_name_or_session_id(agent_name)

        if not agent:
            return make_response(jsonify({'error': 'agent name %s not found' % (agent_name)}), 404)

        new_name = request.json['newname']

        try:
            result = main.agents.rename_agent(agent_name, new_name)

            if not result:
                return make_response(jsonify({
                                                 'error': 'error in renaming %s to %s, new name may have already been used' % (
                                                 agent_name, new_name)}), 400)

            return jsonify({'success': True})

        except Exception:
            return make_response(jsonify({'error': 'error in renaming %s to %s' % (agent_name, new_name)}), 400)

    @app.route('/api/agents/<string:agent_name>/clear', methods=['POST', 'GET'])
    def task_agent_clear(agent_name):
        """
        Clears the tasking buffer for the specified agent.
        """
        agent = main.agents.get_agent_from_name_or_session_id(agent_name)

        if agent is None:
            return make_response(jsonify({'error': 'agent name %s not found' % (agent_name)}), 404)

        main.agents.clear_agent_tasks_db(agent_name)

        return jsonify({'success': True})

    @app.route('/api/agents/<string:agent_name>/kill', methods=['POST', 'GET'])
    def task_agent_kill(agent_name):
        """
        Tasks the specified agent to exit.
        """
        agent = main.agents.get_agent_from_name_or_session_id(agent_name)

        if agent is None:
            return make_response(jsonify({'error': 'agent name %s not found' % (agent_name)}), 404)

        # task the agent to exit
        msg = "tasked agent %s to exit" % (agent.session_id)
        main.agents.save_agent_log(agent.session_id, msg)
        main.agents.add_agent_task_db(agent.session_id, 'TASK_EXIT', uid=g.user['id'])

        return jsonify({'success': True})

    @app.route('/api/agents/<string:agent_name>/notes', methods=['POST'])
    def update_agent_notes(agent_name):
        """
        Update notes on specified agent.
        {"notes" : "notes here"}
        """

        if not request.json:
            return make_response(jsonify({'error': 'request body must be valid JSON'}), 400)

        if not 'notes' in request.json:
            return make_response(jsonify({'error': 'JSON body must include key "notes"'}), 400)

        agent = main.agents.get_agent_from_name_or_session_id(agent_name)
        if not agent:
            return make_response(jsonify({'error': f'Agent not found with name {agent_name}'}))

        agent.notes = request.json['notes']
        Session().commit()

        return jsonify({'success': True})

    @app.route('/api/creds', methods=['GET'])
    def get_creds():
        """
        Returns JSON describing the credentials stored in the backend database.
        """
        credential_list = []
        credentials_raw = Session().query(models.Credential).all()

        for credential in credentials_raw:
            credential_list.append({"ID": credential.id, "credtype": credential.credtype, "domain": credential.domain,
                                    "username": credential.username, "password": credential.password,
                                    "host": credential.host, "os": credential.os, "sid": credential.sid,
                                    "notes": credential.notes})

        return jsonify({'creds': credential_list})

    @app.route('/api/creds', methods=['POST'])
    def add_creds():
        """
        Adds credentials to the database
        """
        if not request.json:
            return make_response(jsonify({'error': 'request body must be valid JSON'}), 400)

        if not 'credentials' in request.json:
            return make_response(jsonify({'error': 'JSON body must include key "credentials"'}), 400)

        creds = request.json['credentials']

        if not type(creds) == list:
            return make_response(jsonify({'error': 'credentials must be provided as a list'}), 400)

        required_fields = ["credtype", "domain", "username", "password", "host"]
        optional_fields = ["OS", "notes", "sid"]

        for cred in creds:
            # ensure every credential given to us has all the required fields
            if not all(k in cred for k in required_fields):
                return make_response(jsonify({'error': 'invalid credential %s' % (cred)}), 400)

            # ensure the type is either "hash" or "plaintext"
            if not (cred['credtype'] == u'hash' or cred['credtype'] == u'plaintext'):
                return make_response(
                    jsonify({'error': 'invalid credential type in %s, must be "hash" or "plaintext"' % (cred)}), 400)

        # other than that... just assume everything is valid

        # this would be way faster if batched but will work for now
        for cred in creds:
            # get the optional stuff, if it's there
            try:
                os = cred['os']
            except KeyError:
                os = ''

            try:
                sid = cred['sid']
            except KeyError:
                sid = ''

            try:
                notes = cred['notes']
            except KeyError:
                notes = ''

            main.credentials.add_credential(
                cred['credtype'],
                cred['domain'],
                cred['username'],
                cred['password'],
                cred['host'],
                os,
                sid,
                notes
            )

        return jsonify({'success': '%s credentials added' % len(creds)})

    @app.route('/api/reporting', methods=['GET'])
    def get_reporting():
        """
        Returns JSON describing the reporting events from the backend database.
        """
        # Add filters for agent, event_type, and MAYBE a like filter on msg
        reporting_raw = main.run_report_query()
        reporting_events = []

        for reporting_event in reporting_raw:
            reporting_events.append(
                {"timestamp": reporting_event.timestamp, "event_type": reporting_event.event_type, "username": reporting_event.username, "agent_name": reporting_event.agent_name,
                 "host_name": reporting_event.hostname, "taskID": reporting_event.taskID, "task": reporting_event.task, "results": reporting_event.results})

        return jsonify({'reporting': reporting_events})

    @app.route('/api/reporting/generate', methods=['POST'])
    def generate_report():
        """
        Generates reports on the backend database.
        Takes {'logo':'directory_location'}
        """
        if not request.json:
            return make_response(jsonify({'error': 'request body must be valid JSON'}), 400)

        directory_location = request.json['logo']

        main.do_report(directory_location)
        return jsonify({'success': True})

    @app.route('/api/reporting/agent/<string:reporting_agent>', methods=['GET'])
    def get_reporting_agent(reporting_agent):
        """
        Returns JSON describing the reporting events from the backend database for
        the agent specified by reporting_agent.
        """

        # first resolve the supplied name to a sessionID
        session_id = Session().query(models.Agent.session_id).filter(models.Agent.name == reporting_agent).scalar()
        if not session_id:
            return jsonify({'reporting': ''})

        # lots of confusion around name/session_id in these queries.
        reporting_raw = Session().query(models.Reporting).filter(models.Reporting.name.contains(session_id)).all()
        reporting_events = []

        for reporting_event in reporting_raw:
            reporting_events.append(
                {"ID": reporting_event.id, "agentname": reporting_event.name, "event_type": reporting_event.event_type,
                 "message": json.loads(reporting_event.message), "timestamp": reporting_event.timestamp, "taskID": reporting_event.taskID})

        return jsonify({'reporting': reporting_events})

    @app.route('/api/reporting/type/<string:event_type>', methods=['GET'])
    def get_reporting_type(event_type):
        """
        Returns JSON describing the reporting events from the backend database for
        the event type specified by event_type.
        """
        reporting_raw = Session().query(models.Reporting).filter(models.Reporting.event_type == event_type).all()
        reporting_events = []

        for reporting_event in reporting_raw:
            reporting_events.append(
                {"ID": reporting_event.id, "agentname": reporting_event.name, "event_type": reporting_event.event_type,
                 "message": json.loads(reporting_event.message), "timestamp": reporting_event.timestamp,
                 "taskID": reporting_event.taskID})

        return jsonify({'reporting': reporting_events})

    @app.route('/api/reporting/msg/<string:msg>', methods=['GET'])
    def get_reporting_msg(msg):
        """
        Returns JSON describing the reporting events from the backend database for
        the any messages with *msg* specified by msg.
        """
        reporting_raw = Session().query(models.Reporting).filter(models.Reporting.message.contains(msg)).all()
        reporting_events = []

        for reporting_event in reporting_raw:
            reporting_events.append(
                {"ID": reporting_event.id, "agentname": reporting_event.name, "event_type": reporting_event.event_type,
                 "message": json.loads(reporting_event.message), "timestamp": reporting_event.timestamp,
                 "taskID": reporting_event.taskID})

        return jsonify({'reporting': reporting_events})

    @app.route('/api/admin/login', methods=['POST'])
    def server_login():
        """
        Takes a supplied username and password and returns the current API token
        if authentication is accepted.
        """
        if not request.json or not 'username' in request.json or not 'password' in request.json:
            abort(400)

        supplied_username = request.json['username']
        supplied_password = request.json['password']

        # try to prevent some basic bruting
        time.sleep(2)
        token = main.users.user_login(supplied_username, supplied_password)

        if token:
            return jsonify({'token': token})
        else:
            return make_response('', 401)

    @app.route('/api/admin/logout', methods=['POST'])
    def server_logout():
        """
        Logs out current user
        """
        main.users.user_logout(g.user['id'])
        return jsonify({'success': True})

    @app.route('/api/admin/restart', methods=['GET', 'POST', 'PUT'])
    def signal_server_restart():
        """
        Signal a restart for the Flask server and any Empire instance.
        """
        restart_server()
        return jsonify({'success': True})

    @app.route('/api/admin/shutdown', methods=['GET', 'POST', 'PUT'])
    def signal_server_shutdown():
        """
        Signal a restart for the Flask server and any Empire instance.
        """
        shutdown_server()
        return jsonify({'success': True})

    @app.route('/api/admin/options', methods=['POST'])
    def set_admin_options():
        """
        Obfuscate all future powershell commands run on all agents.
        """
        if not request.json:
            return make_response(jsonify({'error': 'request body must be valid JSON'}), 400)

        # Set global obfuscation
        if 'obfuscate' in request.json:
            if request.json['obfuscate'].lower() == 'true':
                main.obfuscate = True
            else:
                main.obfuscate = False

        # if obfuscate command is given then set, otherwise use default
        if 'obfuscate_command' in request.json:
            main.obfuscateCommand = request.json['obfuscate_command']

        # add keywords to the obfuscation database
        if 'keyword_obfuscation' in request.json:
            keyword = request.json['keyword_obfuscation']
            try:
                # if no replacement given then generate a random word
                if not request.json['keyword_replacement']:
                    keyword_replacement = random.choice(string.ascii_uppercase) + ''.join(
                        random.choice(string.ascii_uppercase + string.digits) for _ in range(4))
                else:
                    keyword_replacement = request.json['keyword_replacement']
                Session().add(models.Function(keyword=keyword, keyword_replacement=keyword_replacement))
                Session().commit()
            except Exception:
                print(helpers.color("couldn't connect to Database"))

        return jsonify({'success': True})

    @app.route('/api/users', methods=['GET'])
    def get_users():
        """
        Returns JSON of the users from the backend database.
        """
        users_raw = Session().query(models.User).all()

        user_report = []

        for reporting_users in users_raw:
            data = {"ID": reporting_users.id, "username": reporting_users.username,
                    "last_logon_time": reporting_users.last_logon_time, "enabled": reporting_users.enabled,
                    "admin": reporting_users.admin}
            user_report.append(data)

        return jsonify({'users': user_report})

    @app.route('/api/users/<int:uid>', methods=['GET'])
    def get_user(uid):
        """
        return the user for an id
        """
        user = Session().query(models.User).filter(models.User.id == uid).first()

        if user is None:
            make_response(jsonify({'error': 'user %s not found' % uid}), 404)

        return jsonify(
            {"ID": user.id, "username": user.username, "last_logon_time": user.last_logon_time, "enabled": user.enabled,
             "admin": user.admin, "notes": user.notes})

    @app.route('/api/users/me', methods=['GET'])
    def get_user_me():
        """
        Returns the current user.
        """
        return jsonify(g.user)

    @app.route('/api/users', methods=['POST'])
    def create_user():
        # Check that input is a valid request
        if not request.json or not 'username' in request.json or not 'password' in request.json:
            abort(400)

        # Check if user is an admin
        if not main.users.is_admin(g.user['id']):
            abort(403)

        status = main.users.add_new_user(request.json['username'], request.json['password'])
        return jsonify({'success': status})

    @app.route('/api/users/<int:uid>/disable', methods=['PUT'])
    def disable_user(uid):
        # Don't disable yourself
        if not request.json or not 'disable' in request.json or uid == g.user['id']:
            abort(400)

        # User performing the action should be an admin.
        # User being updated should not be an admin.
        if not main.users.is_admin(g.user['id']) or main.users.is_admin(uid):
            abort(403)

        status = main.users.disable_user(uid, request.json['disable'])
        return jsonify({'success': status})

    @app.route('/api/users/<int:uid>/updatepassword', methods=['PUT'])
    def update_user_password(uid):
        if not request.json or not 'password' in request.json:
            abort(400)

        # Must be an admin or updating self.
        if not (main.users.is_admin(g.user['id']) or uid == g.user['id']):
            abort(403)

        status = main.users.update_password(uid, request.json['password'])
        return jsonify({'success': status})

    @app.route('/api/users/<int:uid>/notes', methods=['POST'])
    def update_user_notes(uid):
        """
        Update notes for a user.
        {"notes" : "notes here"}
        """

        if not request.json:
            return make_response(jsonify({'error': 'request body must be valid JSON'}), 400)

        if not 'notes' in request.json:
            return make_response(jsonify({'error': 'JSON body must include key "credentials"'}), 400)

        user = Session().query(models.User).filter(models.User.id == uid).first()
        user.notes = request.json['notes']
        Session().commit()

        return jsonify({'success': True})

    @app.route('/api/plugin/active', methods=['GET'])
    def list_active_plugins():
        """
        Lists all active plugins
        """
        plugins = []

        plugin_path = os.path.abspath("plugins")
        all_plugin_names = [name for _, name, _ in pkgutil.walk_packages([plugin_path])]
        # check if the plugin has already been loaded
        active_plugins = list(empireMenu.loadedPlugins.keys())
        for plugin_name in all_plugin_names:
            if plugin_name in active_plugins:
                data = empireMenu.loadedPlugins[plugin_name].info[0]
                data['options'] = empireMenu.loadedPlugins[plugin_name].options
                plugins.append(data)

        return jsonify({'plugins': plugins})

    @app.route('/api/plugin/<string:plugin_name>', methods=['GET'])
    def get_plugin(plugin_name):
        # check if the plugin has already been loaded
        if plugin_name not in empireMenu.loadedPlugins.keys():
            try:
                empireMenu.do_plugin(plugin_name)
            except:
                return make_response(jsonify({'error': 'plugin %s not found' % (plugin_name)}), 400)
        # get the commands available to the user. This can probably be done in one step if desired
        name = empireMenu.loadedPlugins[plugin_name].get_commands()['name']
        commands = empireMenu.loadedPlugins[plugin_name].get_commands()['commands']
        description = empireMenu.loadedPlugins[plugin_name].get_commands()['description']
        data = {'name': name, 'commands': commands, 'description': description}
        return jsonify(data)

    @app.route('/api/plugin/<string:plugin_name>', methods=['POST'])
    def execute_plugin(plugin_name):
        # check if the plugin has been loaded
        if plugin_name not in empireMenu.loadedPlugins.keys():
            return make_response(jsonify({'error': 'plugin %s not loaded' % (plugin_name)}), 404)

        use_plugin = empireMenu.loadedPlugins[plugin_name]

        # set all passed module options
        for key, value in request.json.items():
            if key not in use_plugin.options:
                return make_response(jsonify({'error': 'invalid module option'}), 400)

            use_plugin.options[key]['Value'] = value

        for option, values in use_plugin.options.items():
            if values['Required'] and ((not values['Value']) or (values['Value'] == '')):
                return make_response(jsonify({'error': 'required module option missing'}), 400)

        results = use_plugin.execute(request.json)
        if results == False:
            return make_response(jsonify({'error': 'internal plugin error'}), 400)
        return jsonify(results)

    if not os.path.exists('./data/empire-chain.pem'):
        print("[!] Error: cannot find certificate ./data/empire-chain.pem")
        sys.exit()

    def shutdown_server():
        """
        Shut down the Flask server and any Empire instance gracefully.
        """
        global serverExitCommand

        print("\n * Shutting down Empire RESTful API")

        if suppress:
            print(" * Shutting down the Empire instance")
            main.shutdown()

        serverExitCommand = 'shutdown'

        func = request.environ.get('werkzeug.server.shutdown')
        if func is not None:
            func()

    def restart_server():
        """
        Restart the Flask server and any Empire instance.
        """
        global serverExitCommand

        shutdown_server()

        serverExitCommand = 'restart'

    def signal_handler(signal, frame):
        """
        Overrides the keyboardinterrupt signal handler so we can gracefully shut everything down.
        """

        global serverExitCommand

        with app.test_request_context():
            shutdown_server()

        serverExitCommand = 'shutdown'

        # repair the original signal handler
        import signal
        signal.signal(signal.SIGINT, signal.default_int_handler)
        sys.exit()

    try:
        signal.signal(signal.SIGINT, signal_handler)
    except ValueError:
        pass

    # wrap the Flask connection in SSL and start it
    certPath = os.path.abspath("./data/")

    # support any version of tls
    pyversion = sys.version_info
    if pyversion[0] == 2 and pyversion[1] == 7 and pyversion[2] >= 13:
        proto = ssl.PROTOCOL_TLS
    elif pyversion[0] >= 3:
        proto = ssl.PROTOCOL_TLS
    else:
        proto = ssl.PROTOCOL_SSLv23

    context = ssl.SSLContext(proto)
    context.load_cert_chain("%s/empire-chain.pem" % (certPath), "%s/empire-priv.key" % (certPath))
    app.run(host='0.0.0.0', port=int(port), ssl_context=context, threaded=True)


def start_sockets(empire_menu: MainMenu, port: int = 5000, suppress: bool = False):
    app = Flask(__name__)
    app.json_encoder = MyJsonEncoder
    socketio = SocketIO(app, cors_allowed_origins="*", json=flask.json)
    empire_menu.socketio = socketio
    room = 'general'  # A socketio user is in the general channel if the join the chat.
    chat_participants = {}
    chat_log = []  # This is really just meant to provide some context to a user that joins the convo.

    # In the future we can expand to store chat messages in the db if people want to retain a whole chat log.

    if suppress:
        # suppress the normal Flask output
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

    def get_user_from_token():
        user = empire_menu.users.get_user_from_token(request.args.get('token', ''))
        if user:
            user['password'] = ''
            user['api_token'] = ''

        return user

    @socketio.on('connect')
    def connect():
        user = get_user_from_token()
        if user:
            print(f"{user['username']} connected to socketio")
            return

        raise ConnectionRefusedError('unauthorized!')

    @socketio.on('disconnect')
    def test_disconnect():
        print('Client disconnected from socketio')

    @socketio.on('chat/join')
    def on_join(data=None):
        """
        The calling user gets added to the "general"  chat room.
        Note: while 'data' is unused, it is good to leave it as a parameter for compatibility reasons.
        The server fails if a client sends data when none is expected.
        :return: emits a join event with the user's details.
        """
        user = get_user_from_token()
        if user['username'] not in chat_participants:
            chat_participants[user['username']] = user
        join_room(room)
        socketio.emit("chat/join", {'user': user,
                                    'username': user['username'],
                                    'message': f"{user['username']} has entered the room."}, room=room)

    @socketio.on('chat/leave')
    def on_leave(data=None):
        """
        The calling user gets removed from the "general" chat room.
        :return: emits a leave event with the user's details.
        """
        user = get_user_from_token()
        if user is not None:
            chat_participants.pop(user['username'], None)
            leave_room(room)
            socketio.emit("chat/leave", {'user': user,
                                         'username': user['username'],
                                         'message': user['username'] + ' has left the room.'}, room=room)

    @socketio.on('chat/message')
    def on_message(data):
        """
        The calling user sends a message.
        :param data: contains the user's message.
        :return: Emits a message event containing the message and the user's username
        """
        user = get_user_from_token()
        chat_log.append({'username': user['username'], 'message': data['message']})
        socketio.emit("chat/message", {'username': user['username'], 'message': data['message']}, room=room)

    @socketio.on('chat/history')
    def on_history(data=None):
        """
        The calling user gets sent the last 20 messages.
        :return: Emit chat messages to the calling user.
        """
        sid = request.sid
        for x in range(len(chat_log[-20:])):
            username = chat_log[x]['username']
            message = chat_log[x]['message']
            socketio.emit("chat/message", {'username': username, 'message': message, 'history': True}, room=sid)

    @socketio.on('chat/participants')
    def on_participants(data=None):
        """
        The calling user gets sent a list of "general" chat participants.
        :return: emit participant event containing list of users.
        """
        sid = request.sid
        socketio.emit("chat/participants", list(chat_participants.values()), room=sid)

    print('')
    print(" * Starting Empire SocketIO on port: {}".format(port))

    cert_path = os.path.abspath("./data/")
    proto = ssl.PROTOCOL_TLS
    context = ssl.SSLContext(proto)
    context.load_cert_chain("{}/empire-chain.pem".format(cert_path), "{}/empire-priv.key".format(cert_path))
    socketio.run(app, host='0.0.0.0', port=port, ssl_context=context)


if __name__ == '__main__':
    args = arguments.args
    database_check_docker()

    if not args.restport:
        args.restport = '1337'
    else:
        args.restport = args.restport[0]

    if not args.socketport:
        args.socketport = '5000'
    else:
        args.socketport = args.socketport[0]

    if args.version:
        print(empire.VERSION)

    if args.reset:
        # Reset called from database/base.py
        sys.exit()

    elif args.headless:
        # start an Empire instance and RESTful API and suppress output
        main = empire.MainMenu(args=args)
        def thread_websocket(empire_menu):
            try:
                start_sockets(empire_menu=empire_menu, suppress=True, port=int(args.socketport))
            except SystemExit as e:
                pass

        thread2 = helpers.KThread(target=thread_websocket, args=(main,))
        thread2.daemon = True
        thread2.start()
        sleep(2)

        try:
            start_restful_api(empireMenu=main, suppress=True, headless=True, username=args.username, password=args.password,
                              port=args.restport)
        except SystemExit as e:
            pass

    elif args.headless:
        # start an Empire instance and RESTful API and suppress output
        main = empire.MainMenu(args=args)
        def thread_websocket(empire_menu):
            try:
                start_sockets(empire_menu=empire_menu, suppress=True, port=int(args.socketport))
            except SystemExit as e:
                pass

        thread2 = helpers.KThread(target=thread_websocket, args=(main,))
        thread2.daemon = True
        thread2.start()
        sleep(2)

        try:
            start_restful_api(empireMenu=main, suppress=True, headless=True, username=args.username, password=args.password,
                              port=args.restport)
        except SystemExit as e:
            pass

    elif args.rest:
        # start an Empire instance and RESTful API
        main = empire.MainMenu(args=args)


        def thread_api(empireMenu):

            try:
                start_restful_api(empireMenu=empireMenu, suppress=False, username=args.username, password=args.password,
                                  port=args.restport)
            except SystemExit as e:
                pass

        thread = helpers.KThread(target=thread_api, args=(main,))
        thread.daemon = True
        thread.start()
        sleep(2)


        def thread_websocket(empire_menu):
            try:
                start_sockets(empire_menu=empire_menu, suppress=False, port=int(args.socketport))
            except SystemExit as e:
                pass

        thread2 = helpers.KThread(target=thread_websocket, args=(main,))
        thread2.daemon = True
        thread2.start()
        sleep(2)

        main.cmdloop()

    elif args.teamserver:
        # start an Empire instance and RESTful API
        main = empire.MainMenu(args=args)

        def thread_api(empireMenu):

            try:
                start_restful_api(empireMenu=empireMenu, suppress=True, username=args.username, password=args.password,
                                  port=args.restport)
            except SystemExit as e:
                pass

        thread = helpers.KThread(target=thread_api, args=(main,))
        thread.daemon = True
        thread.start()
        sleep(2)

        def thread_websocket(empire_menu):
            try:
                start_sockets(empire_menu=empire_menu, suppress=True, port=int(args.socketport))
            except SystemExit as e:
                pass


        thread2 = helpers.KThread(target=thread_websocket, args=(main,))
        thread2.daemon = True
        thread2.start()
        sleep(2)

        main.info()

    else:
        # normal execution
        main = empire.MainMenu(args=args)
        main.cmdloop()

    sys.exit()
