"""
Ecoforest proxy to transform replies to JSON
"""

import sys, logging, datetime, urllib, urllib2, json, requests, urlparse, os
from os import curdir, sep
from BaseHTTPServer import BaseHTTPRequestHandler
from requests.auth import HTTPBasicAuth

# configuration
DEBUG = False
DEFAULT_PORT = 8998

username = os.environ['ECOFOREST_USERNAME']
passwd = os.environ['ECOFOREST_PASSWORD']
host = os.environ['ECOFOREST_HOST']

print()

ECOFOREST_URL = host + '/recepcion_datos_4.cgi'

if DEBUG:
    FORMAT = '%(asctime)-0s %(levelname)s %(message)s [at line %(lineno)d]'
    logging.basicConfig(level=logging.DEBUG, format=FORMAT, datefmt='%Y-%m-%dT%I:%M:%S')
else:
    FORMAT = '%(asctime)-0s %(message)s'
    logging.basicConfig(level=logging.INFO, format=FORMAT, datefmt='%Y-%m-%dT%I:%M:%S')


class EcoforestServer(BaseHTTPRequestHandler):

    def send(self, response):
        try:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response))
        except:
            self.send_error(500, 'Something went wrong here on the server side.')


    def healthcheck(self):
        self.send({'status': 'ok'})


    def stats(self):
        if DEBUG: logging.debug('GET stats')
        stats = self.ecoforest_stats()
        if stats:
            self.send(stats)
        else:
            self.send_error(500, 'Something went wrong here on the server side.')


    def set_status(self, status):
        if DEBUG: logging.debug('SET STATUS: %s' % (status))
        stats = self.ecoforest_stats()

        # only if 'estado' is off send request to turn on
        if status == "on" and stats['state'] == "off":
            data = self.ecoforest_call('idOperacion=1013&on_off=1')

        # only if 'estado' is on send request to turn off
        if status == "off" and (stats['state'] in ["on", "stand by", "starting"]):
            data = self.ecoforest_call('idOperacion=1013&on_off=0')

        self.send(self.get_status())


    def get_status(self):
        stats = self.ecoforest_stats()
        self.send(stats['state'])


    def set_temp(self, temp):
        if DEBUG: logging.debug('SET TEMP: %s' % (temp))
        if float(temp) < 12:
            temp = "12"
        if float(temp) > 40:
            temp = "30"
        # idOperacion=1019&temperatura
        data = self.ecoforest_call('idOperacion=1019&temperatura=' + temp)
        self.send(self.ecoforest_stats())


    def set_potency(self, potency):
        if DEBUG: logging.debug('SET POTENCY: %s' % (potency))
        if float(potency) < 1:
            potency = "1"
        if float(potency) > 9:
            potency = "9"
        # idOperacion=1004&potencia
        data = self.ecoforest_call('idOperacion=1004&potencia=' + potency)
        self.send(self.ecoforest_stats())


    def ecoforest_stats(self):
        stats = self.ecoforest_call('idOperacion=1002')
        reply = dict(e.split('=') for e in stats.text.split('\n')[:-1]) # discard last line ?
        states = {
            '0'  : 'off',
            '1'  : 'starting',
            '2'  : 'starting',
            '3'  : 'starting',
            '4'  : 'starting',
            '10' : 'starting',
            '5'  : 'pre heating',
            '6'  : 'pre heating',
            '7'  : 'on',
            '8'  : 'shutting down',
            '11' : 'shutting down',
            '-3' : 'shutting down',
            '-20': 'stand by',
            '-4' : 'alarm',
        }

        state = reply['estado']
        if state in states:
            reply['state'] = states[state]
        else:
            reply['state'] = 'unknown'
            logging.debug('reply: %s', reply)

        return reply


    def ecoforest_alarms(self):
        result = self.ecoforest_call('idOperacion=1079')
        reply = dict(e.split('=') for e in result.text.split('\n')[:-1]) # discard last line ?

        states = {
            'A012' : 'cpu temp max',
            'A099' : 'pellets',
        }

        state = reply['get_alarmas']
        if state in states:
            reply['alarm'] = states[state]
        else:
            reply['alarm'] = 'unknown'
            logging.debug('reply: %s', reply)

        return reply

    def get_alarms(self):
        if DEBUG: logging.debug('GET alarms')
        stats = self.ecoforest_alarms()
        if stats:
            self.send(stats)
        else:
            self.send_error(500, 'Something went wrong here on the server side.')

    def ecoforest_stats_details(self):
        if DEBUG: logging.debug('ecoforest_stats:\n')
        result = self.ecoforest_call('idOperacion=1020')
        reply = dict(e.split('=') for e in result.text.split('\n')[:-1]) # discard last line ?

        reply_filtered = { k: reply[k] for k in [' Tp'] }

        return reply_filtered

    def get_stats(self):
        if DEBUG: logging.debug('GET stats')
        stats = self.ecoforest_stats_details()
        if stats:
            self.send(stats)
        else:
            self.send_error(500, 'Something went wrong here on the server side.')


    # queries the ecoforest server with the supplied contents and parses the results into JSON
    def ecoforest_call(self, body):
        if DEBUG: logging.debug('Request:\n%s' % (body))
        headers = { 'Content-Type': 'application/json' }
        try:
            request = requests.post(ECOFOREST_URL, data=body, headers=headers, auth=HTTPBasicAuth(username, passwd), timeout=2.5)
            if DEBUG: logging.debug('Request:\n%s' %(request.url))
            if DEBUG: logging.debug('Result:\n%s' %(request.text))
            return request
        except requests.Timeout:
            pass


    def do_POST(self):
        parsed_path = urlparse.urlparse(self.path)
        args = dict()
        if parsed_path.query:
            args = dict(qc.split("=") for qc in parsed_path.query.split("&"))

        if DEBUG: logging.debug('GET: TARGET URL: %s, %s' % (parsed_path.path, parsed_path.query))
        content_len = int(self.headers.getheader('content-length', 0))
        post_body = self.rfile.read(content_len)

        dispatch = {
            '/ecoforest/status': self.set_status,
        }

        # API calls
        if parsed_path.path in dispatch:
            try:
                dispatch[parsed_path.path](post_body, **args)
            except Exception as e:
                if DEBUG: logging.error('POST error:\n%s', exc_info=e)
                self.send_error(500, 'Something went wrong here on the server side.')
        else:
            self.send_error(404,'File Not Found: %s' % parsed_path.path)

        return


    def do_GET(self):
        parsed_path = urlparse.urlparse(self.path)
        args = dict()
        if parsed_path.query:
            args = dict(qc.split("=") for qc in parsed_path.query.split("&"))

        dispatch = {
            '/healthcheck': self.healthcheck,
            '/ecoforest/fullstats': self.stats,
            '/ecoforest/status': self.get_status,
            '/ecoforest/set_status': self.set_status,
            '/ecoforest/set_temp': self.set_temp,
            '/ecoforest/set_potency': self.set_potency,
            '/ecoforest/alarms': self.get_alarms,
            '/ecoforest/stats': self.get_stats,
        }

        # API calls
        if parsed_path.path in dispatch:
            try:
                dispatch[parsed_path.path](**args)
            except Exception as e:
                if DEBUG: logging.error('GET error:\n%s', exc_info=e)
                self.send_error(500, 'Something went wrong here on the server side.')
        else:
            self.send_error(404,'File Not Found: %s' % parsed_path.path)

        return


if __name__ == '__main__':
    try:
        from BaseHTTPServer import HTTPServer
        server = HTTPServer(('', DEFAULT_PORT), EcoforestServer)
        logging.info('Ecoforest proxy server started, with config host (%s) and username (%s)', host, username)
        logging.info('use {Ctrl+C} to shut-down ...')
        server.serve_forever()
    except Exception, e:
        logging.error(e)
        sys.exit(2)
