#!/usr/bin/python
# -*- coding: utf-8 -*-

import google_maps, geometry, helper
import os.path
import cherrypy, json, math, time
from py4j.java_gateway import JavaGateway, GatewayClient
from poi import POI
from route_transport_creator import RouteTransportCreator
from route_footway_creator import RouteFootwayCreator
from route_logger import RouteLogger
from db_control import DBControl
from config import Config
from translator import Translator 

class RoutingWebService():

    def index(self):
        return ''
    index.exposed = True

    @cherrypy.tools.json_in()
    def get_route(self):
        # set gzip header
        cherrypy.response.headers['Content-Type'] = 'application/gzip'
        # create the return tuple
        return_tuple = {}
        return_tuple['route'] = []
        return_tuple['warning'] = ""
        return_tuple['error'] = ""
        translator = Translator(Config().get_param("default_language"))

        # parse json encoded input
        input = helper.convert_dict_values_to_utf8( cherrypy.request.json )

        # options object
        if input.has_key("options") == False:
            return_tuple['error'] = translator.translate("message", "no_route_options")
            return helper.zip_data(return_tuple)
        elif type(input['options']) != type({}):
            return_tuple['error'] = translator.translate("message", "no_route_options")
            return helper.zip_data(return_tuple)
        options = input['options']

        # user language
        language = ""
        if options.has_key("language") == True:
            language = options['language']
        # if the user sends a language, which is not german, take the default language setting
        if language != "de":
            language = Config().get_param("default_language")
        # initialize the translator object with the user's choosen language
        translator = Translator(language)

        # source route
        if input.has_key("source_route") == False:
            return_tuple['error'] = translator.translate("message", "no_source_route")
            return helper.zip_data(return_tuple)
        elif type(input['source_route']) != type([]):
            return_tuple['error'] = translator.translate("message", "no_source_route")
            return helper.zip_data(return_tuple)
        elif input['source_route'].__len__() < 3:
            return_tuple['error'] = translator.translate("message", "source_route_incomplete")
            return helper.zip_data(return_tuple)
        source_route = input['source_route']

        # check if route is valid
        index = 0
        for part in source_route:
            if part['type'] in ["way_point", "intersection", "poi", "station"]:
                index += 1
            elif part['type'] in ["footway", "transport"]:
                index -= 1
            else:
                index = -1
                break
        if index != 1:
            return_tuple['error'] = translator.translate("message", "source_route_incomplete")
            return helper.zip_data(return_tuple)

        # route factor
        if options.has_key("route_factor") == False:
            return_tuple['error'] = translator.translate("message", "no_route_factor_option")
            return helper.zip_data(return_tuple)

        # create session id
        if options.has_key("session_id") == False:
            return_tuple['error'] = translator.translate("message", "no_session_id_option")
            return helper.zip_data(return_tuple)
        session_id = options['session_id']
        # try to cancel prior request
        if Config().has_session_id(session_id):
            Config().query_removement_of_session_id(session_id)
            check_counter = 0
            while Config().has_session_id(session_id):
                time.sleep(1)
                check_counter += 1
                if check_counter >= 5:
                    return_tuple['error'] = translator.translate("message", "old_request_still_running")
                    return helper.zip_data(return_tuple)
            print "check_counter = %d" % check_counter
        if Config().number_of_session_ids() == Config().get_param("thread_pool") - 1:
            return_tuple['error'] = translator.translate("message", "server_busy")
            return helper.zip_data(return_tuple)
        Config().add_session_id(session_id)

        # create route logger object
        route_logger = RouteLogger("routes", "%s-%s" % (source_route[0]['name'].replace(" ", "."), \
                source_route[-1]['name'].replace(" ", ".") ))

        # get a route
        rfc = RouteFootwayCreator(session_id, route_logger, translator)
        return_tuple['route'].append(source_route[0])
        for i in range(1, source_route.__len__(), 2):
            if source_route[i]['type'] == "footway" and source_route[i]['sub_type'] == "footway_place_holder":
                route_part = rfc.find_footway_route(source_route[i-1], source_route[i+1], options['route_factor'])
                if route_part == None:
                    Config().confirm_removement_of_session_id(session_id)
                    route_logger.append_to_log("\n----- result -----\ncanceled")
                    return_tuple['route'] = []
                    return_tuple['error'] = translator.translate("message", "process_canceled")
                    return helper.zip_data(return_tuple)
                route_part.__delitem__(0)
                return_tuple['route'] += route_part
            else:
                return_tuple['route'].append(source_route[i])
                return_tuple['route'].append(source_route[i+1])
        return_tuple['description'] = rfc.get_route_description( return_tuple['route'] )
        route_logger.append_to_log("\n----- result -----\n")
        route_logger.append_to_log( json.dumps( return_tuple['route'], indent=4, encoding="utf-8") + "\n----- end of route -----\n")

        # delete session id
        Config().confirm_removement_of_session_id(session_id)
        # convert return_tuple to json and zip it, before returning
        return helper.zip_data(return_tuple)
    get_route.exposed = True

    @cherrypy.tools.json_in()
    def follow_this_way(self):
        # set gzip header
        cherrypy.response.headers['Content-Type'] = 'application/gzip'
        # create the return tuple
        return_tuple = {}
        return_tuple['route'] = []
        return_tuple['warning'] = ""
        return_tuple['error'] = ""
        translator = Translator(Config().get_param("default_language"))

        # parse json encoded input
        input = helper.convert_dict_values_to_utf8( cherrypy.request.json )

        # options
        if input.has_key("options") == False:
            return_tuple['error'] = translator.translate("message", "no_route_options")
            return helper.zip_data(return_tuple)
        elif type(input['options']) != type({}):
            return_tuple['error'] = translator.translate("message", "no_route_options")
            return helper.zip_data(return_tuple)
        options = input['options']
        # user language
        language = ""
        if options.has_key("language") == True:
            language = options['language']
        # if the user sends a language, which is not german, take the default language setting
        if language != "de":
            language = Config().get_param("default_language")
        # initialize the translator object with the user's choosen language
        translator = Translator(language)

        # start point
        if input.has_key("start_point") == False:
            return_tuple['error'] = translator.translate("message", "no_start_point")
            return helper.zip_data(return_tuple)
        start_point = input['start_point']
        if start_point.has_key("name") == False:
            return_tuple['error'] = translator.translate("message", "start_point_no_name")
            return helper.zip_data(return_tuple)
        elif start_point.has_key("lat") == False:
            return_tuple['error'] = translator.translate("message", "start_point_no_latitude")
            return helper.zip_data(return_tuple)
        elif start_point.has_key("lon") == False:
            return_tuple['error'] = translator.translate("message", "start_point_no_longitude")
            return helper.zip_data(return_tuple)
        elif start_point.has_key("type") == False:
            return_tuple['error'] = translator.translate("message", "start_point_no_type")
            return helper.zip_data(return_tuple)

        # further options
        if options.has_key("way_id") == False:
            return_tuple['error'] = translator.translate("message", "no_way_id")
            return helper.zip_data(return_tuple)
        if options.has_key("bearing") == False:
            return_tuple['error'] = translator.translate("message", "no_bearing_value")
            return helper.zip_data(return_tuple)
        add_all_intersections = False
        if options.has_key("add_all_intersections") == True:
            if options['add_all_intersections'] == "yes":
                add_all_intersections = True
        way = DBControl().fetch_data("SELECT nodes from ways where id = %d" % options['way_id'])
        if way.__len__() == 0:
            return_tuple['error'] = translator.translate("message", "way_id_invalid")
            return helper.zip_data(return_tuple)

        # create session id
        if options.has_key("session_id") == False:
            return_tuple['error'] = translator.translate("message", "no_session_id_option")
            return helper.zip_data(return_tuple)
        session_id = options['session_id']
        # try to cancel prior request
        if Config().has_session_id(session_id):
            Config().query_removement_of_session_id(session_id)
            check_counter = 0
            while Config().has_session_id(session_id):
                time.sleep(1)
                check_counter += 1
                if check_counter >= 5:
                    return_tuple['error'] = translator.translate("message", "old_request_still_running")
                    return helper.zip_data(return_tuple)
            print "check_counter = %d" % check_counter
        if Config().number_of_session_ids() == Config().get_param("thread_pool") - 1:
            return_tuple['error'] = translator.translate("message", "server_busy")
            return helper.zip_data(return_tuple)
        Config().add_session_id(session_id)

        route_logger = RouteLogger("routes", "%s-way_id.%s"
                % (start_point['name'].replace(" ", "."), options['way_id']))

        # get a route
        rfc = RouteFootwayCreator(session_id, route_logger, translator)
        route = rfc.follow_this_way(start_point,
                options['way_id'], options['bearing'], add_all_intersections)
        if route == None:
            return_tuple['error'] = translator.translate("message", "process_canceled")
            route_logger.append_to_log("\n----- result -----\ncanceled")
        else:
            return_tuple['route'] = route
            return_tuple['description'] = rfc.get_route_description( return_tuple['route'] )
            route_logger.append_to_log("\n----- result -----\n")
            route_logger.append_to_log( json.dumps( return_tuple['route'], indent=4, encoding="utf-8") + "\n----- end of route -----\n")

        # convert return_tuple to json and zip it, before returning
        Config().confirm_removement_of_session_id(session_id)
        return helper.zip_data(return_tuple)
    follow_this_way.exposed = True

    @cherrypy.tools.json_in()
    def get_transport_routes(self):
        # set gzip header
        cherrypy.response.headers['Content-Type'] = 'application/gzip'
        # create the return tuple
        return_tuple = {}
        return_tuple['transport_routes'] = []
        return_tuple['warning'] = ""
        return_tuple['error'] = ""
        translator = Translator(Config().get_param("default_language"))

        # parse json encoded input
        input = helper.convert_dict_values_to_utf8( cherrypy.request.json )

        # options object
        if input.has_key("options") == False:
            return_tuple['error'] = translator.translate("message", "no_route_options")
            return helper.zip_data(return_tuple)
        elif type(input['options']) != type({}):
            return_tuple['error'] = translator.translate("message", "no_route_options")
            return helper.zip_data(return_tuple)
        options = input['options']

        # user language
        language = ""
        if options.has_key("language") == True:
            language = options['language']
        # if the user sends a language, which is not german, take the default language setting
        if language != "de":
            language = Config().get_param("default_language")
        # initialize the translator object with the user's choosen language
        translator = Translator(language)

        # source route
        if input.has_key("source_route") == False:
            return_tuple['error'] = translator.translate("message", "no_source_route")
            return helper.zip_data(return_tuple)
        elif type(input['source_route']) != type([]):
            return_tuple['error'] = translator.translate("message", "no_source_route")
            return helper.zip_data(return_tuple)
        elif input['source_route'].__len__() < 3:
            return_tuple['error'] = translator.translate("message", "source_route_incomplete")
            return helper.zip_data(return_tuple)
        source_route = input['source_route']

        # check if route is valid
        index = 0
        number_of_transport_parts = 0
        for part in source_route:
            if part['type'] in ["way_point", "intersection", "poi", "station"]:
                index += 1
            elif part['type'] in ["footway", "transport"]:
                index -= 1
                if part['sub_type'] == "transport_place_holder":
                    number_of_transport_parts += 1
            else:
                index = -1
                break
        if index != 1:
            return_tuple['error'] = translator.translate("message", "source_route_incomplete")
            return helper.zip_data(return_tuple)
        if number_of_transport_parts == 0:
            return_tuple['error'] = translator.translate("message", "source_route_no_transport_parts")
            return helper.zip_data(return_tuple)
        if number_of_transport_parts > 1:
            return_tuple['error'] = translator.translate("message", "source_route_multiple_transport_parts")
            return helper.zip_data(return_tuple)

        # further options
        if options.has_key("number_of_possible_routes") == False:
            options['number_of_possible_routes'] = 3

        # create session id
        if options.has_key("session_id") == False:
            return_tuple['error'] = translator.translate("message", "no_session_id_option")
            return helper.zip_data(return_tuple)
        session_id = options['session_id']
        # try to cancel prior request
        if Config().has_session_id(session_id):
            Config().query_removement_of_session_id(session_id)
            check_counter = 0
            while Config().has_session_id(session_id):
                time.sleep(1)
                check_counter += 1
                if check_counter >= 5:
                    return_tuple['error'] = translator.translate("message", "old_request_still_running")
                    return helper.zip_data(return_tuple)
            print "check_counter = %d" % check_counter
        if Config().number_of_session_ids() == Config().get_param("thread_pool") - 1:
            return_tuple['error'] = translator.translate("message", "server_busy")
            return helper.zip_data(return_tuple)
        Config().add_session_id(session_id)

        # create route logger object
        route_logger = RouteLogger("routes", "%s-%s" % (source_route[0]['name'].replace(" ", "."), \
                source_route[-1]['name'].replace(" ", ".") ))

        # parse route parts
        return_tuple['transport_routes'] = []
        rtc = RouteTransportCreator(session_id, route_logger, translator)
        for i in range(1, source_route.__len__(), 2):
            if source_route[i]['type'] == "footway" and source_route[i]['sub_type'] == "transport_place_holder":
                transport_route_list = rtc.find_transport_route(source_route[i-1], source_route[i+1], options['number_of_possible_routes'])
                break
        if transport_route_list == None:
            Config().confirm_removement_of_session_id(session_id)
            route_logger.append_to_log("\n----- result -----\ncanceled")
            return_tuple['transport_routes'] = []
            return_tuple['error'] = translator.translate("message", "process_canceled")
            return helper.zip_data(return_tuple)
        for route in transport_route_list:
            transport_route = {}
            transport_route['description'] = route.description
            transport_route['route'] = [ source_route[0] ]
            for i in range(1, source_route.__len__(), 2):
                if source_route[i]['type'] == "footway" and source_route[i]['sub_type'] == "transport_place_holder":
                    route_part = route.route
                    route_part.__delitem__(0)
                    transport_route['route'] += route_part
                else:
                    transport_route['route'].append(source_route[i])
                    transport_route['route'].append(source_route[i+1])
            return_tuple['transport_routes'].append(transport_route)
            route_logger.append_to_log("\n----- %s -----\n" % transport_route['description'])
            route_logger.append_to_log( json.dumps( transport_route['route'], indent=4, encoding="utf-8") + "\n----- end of route -----\n\n")

        # convert return_tuple to json and zip it, before returning
        Config().confirm_removement_of_session_id(session_id)
        return helper.zip_data(return_tuple)
    get_transport_routes.exposed = True

    @cherrypy.tools.json_in()
    def get_poi(self):
        # set gzip header
        cherrypy.response.headers['Content-Type'] = 'application/gzip'
        # create the return tuple
        return_tuple = {}
        return_tuple['poi'] = []
        return_tuple['warning'] = ""
        return_tuple['error'] = ""
        translator = Translator(Config().get_param("default_language"))
        # parse json encoded input
        options = helper.convert_dict_values_to_utf8( cherrypy.request.json )

        # user language
        language = ""
        if options.has_key("language") == True:
            language = options['language']
        # if the user sends a language, which is not german, take the default language setting
        if language != "de":
            language = Config().get_param("default_language")
        # initialize the translator object with the user's choosen language
        translator = Translator(language)

        # check latitude, longitude and radius input
        try:
            lat = float(options['lat'])
        except KeyError as e:
            return_tuple['error'] = translator.translate("message", "no_latitude_value")
            return helper.zip_data(return_tuple)
        except ValueError as e:
            return_tuple['error'] = translator.translate("message", "no_latitude_value")
            return helper.zip_data(return_tuple)
        try:
            lon = float(options['lon'])
        except KeyError as e:
            return_tuple['error'] = translator.translate("message", "no_longitude_value")
            return helper.zip_data(return_tuple)
        except ValueError as e:
            return_tuple['error'] = translator.translate("message", "no_longitude_value")
            return helper.zip_data(return_tuple)
        try:
            radius = int(options['radius'])
        except KeyError as e:
            return_tuple['error'] = translator.translate("message", "no_range_value")
            return helper.zip_data(return_tuple)
        except ValueError as e:
            return_tuple['error'] = translator.translate("message", "no_range_value")
            return helper.zip_data(return_tuple)

        # tags and search
        # tag list
        if options.has_key("tags") == False:
            return_tuple['error'] = translator.translate("message", "no_tags_value")
            return helper.zip_data(return_tuple)
        if options['tags'] == "":
            return_tuple['error'] = translator.translate("message", "no_tags_value")
            return helper.zip_data(return_tuple)
        tag_list = options['tags'].split("+")
        # search
        try:
            search = options['search']
        except KeyError as e:
            search = ""

        # create session id
        if options.has_key("session_id") == False:
            return_tuple['error'] = translator.translate("message", "no_session_id_option")
            return helper.zip_data(return_tuple)
        session_id = options['session_id']
        # try to cancel prior request
        if Config().has_session_id(session_id):
            Config().query_removement_of_session_id(session_id)
            check_counter = 0
            while Config().has_session_id(session_id):
                time.sleep(1)
                check_counter += 1
                if check_counter >= 5:
                    return_tuple['error'] = translator.translate("message", "old_request_still_running")
                    return helper.zip_data(return_tuple)
            print "check_counter = %d" % check_counter
        if Config().number_of_session_ids() == Config().get_param("thread_pool") - 1:
            return_tuple['error'] = translator.translate("message", "server_busy")
            return helper.zip_data(return_tuple)
        Config().add_session_id(session_id)

        # get poi
        poi = POI(session_id, translator)
        poi_list = poi.get_poi(lat, lon, radius, tag_list, search)
        if poi_list == None:
            Config().confirm_removement_of_session_id(session_id)
            return_tuple['poi'] = []
            return_tuple['error'] = translator.translate("message", "process_canceled")
            return helper.zip_data(return_tuple)

        # convert return_tuple to json and zip it, before returning
        return_tuple['poi'] = poi_list
        Config().confirm_removement_of_session_id(session_id)
        return helper.zip_data(return_tuple)
    get_poi.exposed = True

    @cherrypy.tools.json_in()
    def get_bug_report(self):
        # set gzip header
        cherrypy.response.headers['Content-Type'] = 'application/gzip'
        # create return tuple
        return_tuple = {}
        return_tuple['status'] = "failed"
        return_tuple['warning'] = ""
        return_tuple['error'] = ""

        # parse json encoded input
        input = helper.convert_dict_values_to_utf8( cherrypy.request.json )

        # user language
        language = ""
        if input.has_key("language") == True:
            language = input['language']
        # if the user sends a language, which is not german, take the default language setting
        if language != "de":
            language = Config().get_param("default_language")
        # initialize the translator object with the user's choosen language
        translator = Translator(language)

        # bug report variables
        if input.has_key("file_name") == False:
            return_tuple['error'] = translator.translate("message", "no_bug_report_file_name")
            return helper.zip_data(return_tuple)
        if input.has_key("bug_report") == False:
            return_tuple['error'] = translator.translate("message", "no_bug_report_contents")
            return helper.zip_data(return_tuple)

        # save bug report
        try:
            bug_report_folder = os.path.join( Config().get_param("logs_folder"), "client")
            file = open(os.path.join(bug_report_folder, input['file_name'].split("/")[-1]), 'w')
            file.write(input['bug_report'])
            file.close()
        except IOError as e:
            pass

        # send mail to the admin
        helper.send_email("OSMRouter: New bug report", "%s\n\n%s"
                % (input['file_name'].split("/")[-1], input['bug_report']) )

        # convert return_tuple to json and zip it, before returning
        return_tuple['status'] = "ok"
        return helper.zip_data(return_tuple)
    get_bug_report.exposed = True

    @cherrypy.tools.json_in()
    def cancel_request(self):
        # set gzip header
        cherrypy.response.headers['Content-Type'] = 'application/gzip'
        # create the return tuple
        return_tuple = {}
        return_tuple['warning'] = ""
        return_tuple['error'] = ""
        translator = Translator(Config().get_param("default_language"))
        # parse json encoded input
        options = helper.convert_dict_values_to_utf8( cherrypy.request.json )
        # create session id
        if options.has_key("session_id") == False:
            return_tuple['error'] = translator.translate("message", "no_session_id_option")
            return helper.zip_data(return_tuple)
        session_id = options['session_id']
        print "cancel session id %s" % session_id
        # try to cancel prior request
        if Config().has_session_id(session_id):
            Config().query_removement_of_session_id(session_id)
        return helper.zip_data(return_tuple)
    cancel_request.exposed = True

    def get_departures(self, lat=None, lon=None, language=None):
        # set gzip header
        cherrypy.response.headers['Content-Type'] = 'application/gzip'
        # create the return tuple
        return_tuple = {}
        return_tuple['departures'] = []
        return_tuple['warning'] = ""
        return_tuple['error'] = ""

        # user language
        # if the user sends a language, which is not german, take the default language setting
        if language != "de":
            language = Config().get_param("default_language")
        # initialize the translator object with the user's choosen language
        translator = Translator(language)

        # check latitude and longitude input
        try:
            lat = float(lat)
        except ValueError as e:
            return_tuple['error'] = translator.translate("message", "no_latitude_value")
            return helper.zip_data(return_tuple)
        try:
            lon = float(lon)
        except ValueError as e:
            return_tuple['error'] = translator.translate("message", "no_longitude_value")
            return helper.zip_data(return_tuple)

        # get the nearest stations for this coordiantes and take the first one
        gateway = JavaGateway(GatewayClient(port=Config().get_param("gateway_port")), auto_field=True)
        main_point = gateway.entry_point
        station_list = main_point.getNearestStations(
                geometry.convert_coordinate_to_int(lat),
                geometry.convert_coordinate_to_int(lon))
        try:
            station = station_list.stations[0]
        except IndexError as e:
            return_tuple['error'] = translator.translate("message", "no_station_for_this_coordinates")
            return helper.zip_data(return_tuple)
        if station.id <= 0:
            return_tuple['error'] = translator.translate("message", "no_station_for_this_coordinates")
            return helper.zip_data(return_tuple)

        # get departures for station
        departures_result = main_point.getDepartures( station.id, 0 )
        if departures_result.status.toString() == "INVALID_STATION":
            return_tuple['error'] = translator.translate("message", "no_station_for_this_coordinates")
            return helper.zip_data(return_tuple)
        if departures_result.status.toString() == "SERVICE_DOWN":
            return_tuple['error'] = translator.translate("message", "bahn_server_down")
            return helper.zip_data(return_tuple)
        date_format = gateway.jvm.java.text.SimpleDateFormat("HH:mm", gateway.jvm.java.util.Locale.GERMAN)
        for station_departure in departures_result.stationDepartures:
            for departure in station_departure.departures:
                dep_entry = {}
                dep_entry['nr'] = departure.line.label
                dep_entry['to'] = departure.destination.name
                dep_entry['time'] = date_format.format(departure.plannedTime)
                # remaining time
                duration = departure.plannedTime.getTime()/1000 - int(time.time())
                minutes, seconds = divmod(duration, 60)
                dep_entry['remaining'] = "%d Min" % minutes
                return_tuple['departures'].append(dep_entry)

        # convert return_tuple to json and zip it, before returning
        return helper.zip_data(return_tuple)
    get_departures.exposed = True

    def get_coordinates(self, address=None, language=None):
        # set gzip header
        cherrypy.response.headers['Content-Type'] = 'application/gzip'
        # create the return tuple
        return_tuple = {}
        return_tuple['coordinates'] = {}
        return_tuple['warning'] = ""
        return_tuple['error'] = ""

        # user language
        # if the user sends a language, which is not german, take the default language setting
        if language != "de":
            language = Config().get_param("default_language")
        # initialize the translator object with the user's choosen language
        translator = Translator(language)

        # check address input string
        if address == None or address == "":
            return_tuple['error'] = translator.translate("message", "no_address_string")
            return helper.zip_data(return_tuple)

        # ask google for address coordinates
        result = google_maps.get_latlon(address)
        if result != None:
            return_tuple['coordinates'] = result
        else:
            return_tuple['error'] = translator.translate("message", "address_invalid")

        # convert return_tuple to json and zip it, before returning
        return helper.zip_data(return_tuple)
    get_coordinates.exposed = True

    def get_address(self, lat=None, lon=None, language=None):
        # set gzip header
        cherrypy.response.headers['Content-Type'] = 'application/gzip'
        # create the return tuple
        return_tuple = {}
        return_tuple['address'] = ""
        return_tuple['warning'] = ""
        return_tuple['error'] = ""

        # user language
        # if the user sends a language, which is not german, take the default language setting
        if language != "de":
            language = Config().get_param("default_language")
        # initialize the translator object with the user's choosen language
        translator = Translator(language)

        # check latitude and longitude input
        try:
            lat = float(lat)
        except ValueError as e:
            return_tuple['error'] = translator.translate("message", "no_latitude_value")
            return helper.zip_data(return_tuple)
        try:
            lon = float(lon)
        except ValueError as e:
            return_tuple['error'] = translator.translate("message", "no_longitude_value")
            return helper.zip_data(return_tuple)

        # ask google for an address to  the given coordinates
        result = google_maps.get_address(lat, lon, True)
        if result != None:
            return_tuple['address'] = result
        else:
            return_tuple['error'] = translator.translate("message", "no_address_for_this_coordinates")

        # convert return_tuple to json and zip it, before returning
        return helper.zip_data(return_tuple)
    get_address.exposed = True

    def get_all_supported_poi_tags(self):
        # set gzip header
        cherrypy.response.headers['Content-Type'] = 'application/gzip'
        # create the return tuple
        return_tuple = {}
        return_tuple['supported_poi_tags'] = "favorites+transport+food+tourism+shop+health" \
                "+entertainment+finance+education+public_service+named_intersection+other_intersection" \
                "+traffic_signals+trash"
        return_tuple['warning'] = ""
        return_tuple['error'] = ""
        # convert return_tuple to json and zip it, before returning
        return helper.zip_data(return_tuple)
    get_all_supported_poi_tags.exposed = True

    def get_version(self):
        # set gzip header
        cherrypy.response.headers['Content-Type'] = 'application/gzip'
        # create the return tuple
        return_tuple = {}
        return_tuple['warning'] = ""
        return_tuple['error'] = ""
        return_tuple['interface'] = 0.1
        return_tuple['server'] = 0.1
        # try to get map version
        return_tuple['map_version'] = ""
        map_version_file = os.path.join(Config().get_param("maps_folder"), "state.txt.productive")
        if os.path.exists(map_version_file):
            file = open(map_version_file, 'r')
            for line in file.readlines():
                if line.startswith("timestamp"):
                    return_tuple['map_version'] = line.split("=")[1].split("T")[0]
                    break
            file.close()
        # convert return_tuple to json and zip it, before returning
        return helper.zip_data(return_tuple)
    get_version.exposed = True

###################
### start webserver
if __name__ == '__main__':
    cherrypy.config['server.socket_host'] = Config().get_param("host")
    cherrypy.config['server.socket_port'] = Config().get_param("port")
    cherrypy.config['server.thread_pool'] = Config().get_param("thread_pool")
    cherrypy.config['tools.encode.on'] = True
    cherrypy.config['tools.encode.encoding'] = "utf-8"
    cherrypy.quickstart( RoutingWebService() )