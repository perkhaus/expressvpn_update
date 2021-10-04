#!/usr/bin/env python3
"""
Python script to download/verify updates to the ExpressVPN Linux executable.
Credentials are best not stored within the script. For more information...
https://dev.to/biplov/handling-passwords-and-secret-keys-using-environment-variables-2ei0
"""
#
# Copyright 2021, BK Perkins, all rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>.
#

import sys, os
if hasattr(sys,'ps1') and os.geteuid() != 0:
  exit('\nThis script can only be run as root (or sudo).\n')

# -------------------------------------------------------------------------------------------------
# user configurable variables
# -------------------------------------------------------------------------------------------------
email_enabled = True
if(email_enabled):
  email_user = os.getenv('EXPRESSVPN_EMAIL_USER')      or 'username'
  email_pass = os.getenv('EXPRESSVPN_EMAIL_PASS')      or 'password'
  email_domain = os.getenv('EXPRESSVPN_EMAIL_DOMAIN')  or 'gmail.com'
  email_from = os.getenv('EXPRESSVPN_EMAIL_FROM')      or email_user + '@' + email_domain
  email_to = os.getenv('EXPRESSVPN_EMAIL_TO')          or email_from
  email_server = os.getenv('EXPRESSVPN_EMAIL_SERVER')  or 'smtp.' + email_domain
  email_port = int(os.getenv('EXPRESSVPN_EMAIL_PORT')) or 587
# -------------------------------------------------------------------------------------------------

# import libraries
from genericpath import exists
from urllib.request import urlopen
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import re, requests, shutil, smtplib, pwd, subprocess

# build required variables
download_path = '/var/local'              # non-interactive: e.g. cron (root)
urlSource = 'https://www.expressvpn.com/latest?utm_source=linux_app#linux'
os_versions = ('Ubuntu 64-bit', 'Ubuntu 32-bit', 'Fedora 64-bit', 'Fedora 32-bit', 'Arch 64-bit', 'Raspbian 32-bit')
os_chosen = os_versions[0]                # default: 0 ('Ubuntu 64-bit')
os_hostname = os.uname().nodename
os_username = pwd.getpwuid(os.getuid()).pw_name


# functions
def download_file(url: str, local_filename: str) -> int:
  errnum = 0
  try:
    with requests.get(url, stream=True, timeout=60) as r:
      with open(local_filename, 'wb') as f:
          shutil.copyfileobj(r.raw, f)
    #os.chmod(local_filename, 0o777)
  #except shutil.Error as e:
  #  errnum = e.errno
  #except Exception as e:
  #  errnum = e.args[0]
  finally:
    pass
  return errnum

def getLocalFilename(url):
  local_file = ''
  try:
    local_file = url.split('/')[-1] # indeterminate path, possibly location of script
    if(exists(download_path)):
      local_file = os.path.join(download_path, local_file)
    elif not hasattr(sys, 'ps1'):
      local_file = os.path.join(os.path.expanduser('~'), local_file)
  finally:
    pass
  return local_file

def find_installation_file(url):
  page = urlopen(url, timeout=10)
  html = page.read().decode("utf-8")
  pattern = '<option.*?>.*?' + os_chosen + '.*?</option.*?>'
  match_results = re.search(pattern, html, re.IGNORECASE)
  if(match_results):
    option_tag = match_results.group()
    match_results = re.search("value=[\'\"]+(.*?)[\'\"]+>", option_tag, re.IGNORECASE)
    return match_results.group(1)

def find_signature_file(url):
  page = urlopen(url, timeout=10)
  html = page.read().decode("utf-8")
  pattern = '<option.*?>.*?' + os_chosen + '.*?</option.*?>'
  match_results = re.search(pattern, html, re.IGNORECASE)
  if(match_results):
    option_tag = match_results.group()
    match_results = re.search("data-signature-uri=[\'\"](.*?)[\'\"]", option_tag, re.IGNORECASE)
    return match_results.group(1)

def smtp_error(x):
  return {
      534: 'See... https://serverfault.com/questions/635139/how-to-fix-send-mail-authorization-failed-534-5-7-14',
      535: 'Username and Password not accepted.'
  }.get(x, 'Unhandled error... see... https://support.google.com/a/answer/3726730')

def send_email(subject: str, body: str) -> None:
  """
  Sends email with subject, body

  Returns: None
  
  Keyword arguments:
  subject -- the email subject
  body -- the email body in plaintext
  """
  #compose some of the basic message headers:
  msg = MIMEMultipart()
  msg['From'] = email_from
  msg['To'] = email_to
  msg['Subject'] = subject

  #attach the body of the email to the MIME message
  msg.attach(MIMEText(body, 'plain'))

  #send using the SMTP server
  try:
    server = smtplib.SMTP(email_server, email_port, timeout=10)
    server.ehlo()
    server.starttls()
    server.ehlo()
    server.login(email_user, email_pass)
    server.sendmail(email_from, email_to, msg.as_string())
  except Exception as e:
      #logger.exception(e)
      errno = e.args[0]
      print('Error(' + str(errno) + '), ' + smtp_error(errno) )
  finally:
    server.quit() 
  return

def gpg(operations:list):
  """Executes gpg to check signature"""
  parameter_list = []
  parameter_list.append('gpg')
  if operations:
    for operation in operations:
      parameter_list.append(operation)
  try:
    return_val = subprocess.check_output(parameter_list)
  except Exception as e:
    return_val = e.args[0]
  return return_val

def main():
  subject = ''
  body = ''
  sig_found = False
  urlSignature = find_signature_file(urlSource)
  if(urlSignature):
    signature_file = getLocalFilename(urlSignature)
    if(not exists(signature_file)):
      download_file(urlSignature, signature_file)
    sig_found = True
  urlTarget = find_installation_file(urlSource)
  if(urlTarget):
    update_file = getLocalFilename(urlTarget)
    if(not exists(update_file)):
      download_file(urlTarget, update_file)
      subject = 'ExpressVPN Update Available'
      body =  'Host: ' + os.uname().nodename + '\n$ sudo dpkg -i ' + update_file
      if(sig_found):
        gpg(['--keyserver', 'hkp://keyserver.ubuntu.com', '--recv-keys', '0xAFF2A1415F6A3A38'])
        #fingerprint = gpg(['--fingerprint', 'release@expressvpn.com']).decode().splitlines()[1].strip()
        # returns empty bytes on success
        if(b'' == gpg(['--verify', signature_file])):
          body += '\nSignature verified'
        else:
          body += '\nWARNING! Signature NOT verified!'
      #todo: ?install file?
    else: # file already exists
      print('Latest update already downloaded:',update_file)
      return # do nothing
  else: # no target url found
    subject = 'ExpressVPN Update FAILED'
    body = 'Could not locate target URL for OS (' + os_chosen + ') on page...\n' + urlSource
  print(subject, '-', body)
  if(email_enabled):
    send_email(subject, body)
  return


# run main()
if __name__ == '__main__':
    main()