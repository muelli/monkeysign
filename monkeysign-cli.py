#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Sign a key in a safe fashion.

This command should sign a key based on the fingerprint or user id
specified on the commandline, encrypt the result and mail it to the
user. This leave the choice of publishing the certification to that
person and makes sure that person owns the identity signed. This
script assumes you have gpg-agent configure to prompt for passwords.
"""
# see the optparse below for the remaining arguments

import sys

from optparse import OptionParser, TitledHelpFormatter
from gpg import Keyring, TempKeyring
from email.mime.multipart import MIMEMultipart
from email.mime.message import MIMEMessage
from email.mime.application import MIMEApplication
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
import smtplib
import subprocess

def parse_args():
    """parse the commandline arguments"""
    parser = OptionParser(description=__doc__, usage='%prog [options] <keyid>', 
                          epilog='<keyid>: a GPG fingerprint or key id')
    parser.add_option('-d', '--debug', dest='debug', default=False, action='store_true',
                      help='request debugging information from GPG engine (lots of garbage)')
    parser.add_option('-v', '--verbose', dest='verbose', default=False, action='store_true',
                      help='explain what we do along the way')
    parser.add_option('-n', '--dry-run', dest='dryrun', default=False, action='store_true',
                      help='do not actually do anything')
    parser.add_option('-u', '--user', dest='user', help='user id to sign the key with')
    parser.add_option('-a', '--all', dest='alluids', default=False, action='store_true',
                      help='sign all uids on key')
    parser.add_option('-l', '--local', dest='local', default=False, action='store_true',
                      help='import in normal keyring a local certification')
    parser.add_option('-k', '--keyserver', dest='keyserver',
                      help='keyserver to fetch keys from')
    parser.add_option('-s', '--smtp', dest='smtpserver', help='SMTP server to use')
    parser.add_option('--no-mail', dest='nomail', default=False, action='store_true',
                      help='Do not send email at all. (Default is to use sendmail.)')
    parser.add_option('-t', '--to', dest='to', 
                      help='Override destination email for testing (default is to use the first uid on the key or send email to each uid chosen)')

    return parser.parse_args()

class MonkeysignCli():

    # the options that determine how we operate, from the parse_args()
    options = {}

    # the key we are signing, can be a keyid or a uid pattern
    pattern = None

    # the regular keyring we suck secrets and maybe the key to be signed from
    keyring = None

    # the temporary keyring we operate in
    tmpkeyring = None

    # the fingerprints that we actually signed
    signed_keys = None

    def main(self,pattern, options = {}):
        """main code execution loop

        we expect to have the commandline parsed for us

        General process
        ===============

        1. fetch the key into a temporary keyring
        1.a) if allowed (@todo), from the keyservers
        1.b) from the local keyring (@todo try that first?)
        2. copy the signing key secrets into the keyring
        3. for every user id (or all, if -a is specified)
        3.1. sign the uid, using gpg-agent
        3.2. export and encrypt the signature
        3.3. mail the key to the user
        3.4. optionnally (-l), create a local signature and import in
        local keyring
        4. trash the temporary keyring
        """
        self.options = options
        self.pattern = pattern
        self.signed_keys = {}

        if options.local:
            raise NotImplementedError('local key signing not implemented yet')
        if not options.alluids:
            raise NotImplementedError('per uid signatures not supported yet, please use -a for now')

        # setup environment and options
        self.tmpkeyring = tmpkeyring = TempKeyring()
        self.keyring = Keyring() # the real keyring
        if options.debug:
            self.tmpkeyring.context.debug = sys.stderr
        if options.keyserver is not None: tmpkeyring.context.set_option('keyserver', options.keyserver)

        if options.user is None:
            keys = self.keyring.get_keys(None, True)
            for fpr, key in keys.iteritems():
                if not key.invalid and not key.disabled and not key.expired and not key.revoked:
                    options.user = key.uids.values()[0].uid
                    break

            if options.user is None:
                print >>sys.stderr, 'no default secret key found, abort!'
                sys.exit(1)

        print "Using your identity:", options.user

        # 1. fetch the key into a temporary keyring
        self.find_key()

        # 2. copy the signing key secrets into the keyring
        self.copy_secrets()

        # 3. for every user id (or all, if -a is specified)
        # @todo select the uid
        # 3.1. sign the uid, using gpg-agent
        self.sign_key()

        # 3.2. export and encrypt the signature
        # 3.3. mail the key to the user
        self.export_key()

        # 3.4. optionnally (-l), create a local signature and import in
        #local keyring
        # @todo

        # 4. trash the temporary keyring
        if options.verbose: print >>sys.stderr, 'deleting the temporary keyring ', tmpkeyring.tmphomedir
        # implicit

    def find_key(self):
        """find the key to be signed somewhere"""
        self.keyring.context.set_option('export-options', 'export-minimal')
        if self.options.keyserver:
            # 1.a) if allowed, from the keyservers
            if options.verbose: print >>sys.stderr, 'fetching key %s from keyservers' % self.pattern
            if self.options.dryrun: return True

            if not re.search('^[0-9A-F]*$', self.pattern): # this is not a keyid
                # the problem here is that we need to implement --search-keys, and it's a pain
                raise NotImplementedError('please provide a keyid or fingerprint, uids are not supported yet')

            if not self.tmpkeyring.fetch_keys(self.pattern) \
                    and not self.tmpkeyring.import_data(self.keyring.export_data(self.pattern, True)):
                print >>sys.stderr, 'failed to get key %s from keyservers or from your keyring, aborting' % pattern
                sys.exit(4)
        else:
            # 1.b) from the local keyring (@todo try that first?)
            if self.options.verbose: print >>sys.stderr, 'looking for key %s in your keyring' % self.pattern
            if self.options.dryrun: return True
            if not self.tmpkeyring.import_data(self.keyring.export_data(self.pattern)):
                print >>sys.stderr, 'could not find key %s in your keyring, and no keyserve defined' % self.pattern
                sys.exit(3)


    def copy_secrets(self):
        """import secret keys from your keyring"""
        if self.options.verbose: print >>sys.stderr, 'copying your private key to temporary keyring in', self.tmpkeyring.tmphomedir
        if not self.options.dryrun:
            if not self.tmpkeyring.import_data(self.keyring.export_data(options.user, True)):
                print >>sys.stderr, 'could not find private key material, do you have a GPG key?'
                sys.exit(5)

    def sign_key(self):
        """sign the key uids, as specified"""

        keys = self.tmpkeyring.get_keys(self.pattern)

        print "found", len(keys), "keys matching your request"

        for key in keys:
            print 'Signing the following key'
            print
            print str(keys[key])
            print

            print 'Sign key? [y/N] ',
            ans = sys.stdin.readline()
            while ans == "\n":
                print 'Sign key? [y/N] ',
                ans = sys.stdin.readline()

            if ans.lower() != "y\n":
                print >>sys.stderr, 'aborting keysigning as requested'
                continue

            if not self.options.dryrun:
                if not self.tmpkeyring.sign_key(keys[key].fpr, options.alluids):
                    print >>sys.stderr, 'key signing failed'
                else:
                    self.signed_keys[key] = keys[key]

    def export_key(self):
        self.tmpkeyring.context.set_option('armor')
        self.tmpkeyring.context.set_option('always-trust')

        if '@' in options.user:
            from_user = options.user
        else:
            from_key = self.tmpkeyring.get_keys(options.user).values()[0]        
            from_user = from_key.uids.values()[0].uid

        for fpr in self.signed_keys:
            data = self.tmpkeyring.export_data(fpr)

            # first layer, seen from within:
            # an encrypted MIME message, made of two parts: the
            # introduction and the signed key material
            text = MIMEText('your pgp key, yay', 'plain', 'utf-8')
            filename = "yourkey.asc" # should be 0xkeyid.uididx.signed-by-0xkeyid.asc
            key = MIMEBase('application', 'php-keys', name=filename)
            key.add_header('Content-Disposition', 'attachment', filename=filename)
            key.add_header('Content-Transfer-Encoding', '7bit')
            key.add_header('Content-Description', 'PGP Key <keyid>, uid <uid> (<idx), signed by <keyid>')
            message = MIMEMultipart('mixed', [text, data])
            encrypted = self.tmpkeyring.encrypt_data(message.as_string(), self.pattern)

            # the second layer up, made of two parts: a version number
            # and the first layer, encrypted
            p1 = MIMEBase('application', 'pgp-encrypted', filename='signedkey.msg')
            p1.add_header('Content-Disposition','attachment', filename='signedkey.msg')
            p1.set_payload('Version: 1')
            p2 = MIMEBase('application', 'octet-stream', filename='msg.asc')
            p2.add_header('Content-Disposition', 'inline', filename='msg.asc')
            p2.add_header('Content-Transfer-Encoding', '7bit')
            p2.set_payload(encrypted)
            msg = MIMEMultipart('encrypted', None, [p1, p2], protocol="application/pgp-encrypted")
            msg['Subject'] = 'Your signed OpenPGP key'
            msg['From'] = from_user
            msg.preamble = 'This is a multi-part message in PGP/MIME format...'
            # take the first uid, not ideal
            if not self.options.to:
                self.options.to = self.signed_keys[fpr].uids.values()[0].uid
            msg['To'] = self.options.to

            if self.options.smtpserver is not None:
                if self.options.verbose: print >>sys.stderr, 'sending message through SMTP server', self.options.smtpserver
                if self.options.dryrun: return True
                server = smtplib.SMTP(self.options.smtpserver)
                server.sendmail(from_user, self.options.to, msg.as_string())
                server.set_debuglevel(1)
                server.quit()
            elif not self.options.nomail:
                if self.options.verbose: print >>sys.stderr, 'sending message through sendmail'
                if self.options.dryrun: return True
                p = subprocess.Popen(['/usr/sbin/sendmail', '-t'], stdin=subprocess.PIPE)
                p.communicate(msg.as_string())
            else:
                # okay, no mail, just dump the exported key then
                print data

if __name__ == '__main__':
    (options, args) = parse_args()
    try:
        MonkeysignCli().main(args[0], options)
    except IndexError:
        print >>sys.stderr, 'wrong number of arguments'
        sys.exit(1)
    except NotImplementedError as e:
        print >>sys.stderr, str(e)
        sys.exit(2)
