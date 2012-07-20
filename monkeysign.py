import os, tempfile, shutil, subprocess, re

class KeyNotFound(Exception):
        def __init__(self, msg=None):
                self.msg = msg
        def __repr__(self):
                return self.msg

class Gpg():
        """Python wrapper for GnuPG

        This wrapper allows for a simpler interface than GPGME or PyME
        to GPG, and bypasses completely GPGME to interoperate directly
        with GPG as a process.

        It uses the gpg-agent to prompt for passphrases and
        communicates with GPG over the stdin for commnads
        (--command-fd) and stdout for status (--status-fd).
        """

        # the gpg binary to call
        gpg_binary = 'gpg'

        # a list of key => value commandline options
        #
        # to pass a flag without options, use None as the value
        options = {}

        def __init__(self, homedir=None):
                """f"""
                self.options = { 'status-fd': 1,
                            'command-fd': 0,
                            'no-tty': None,
                            'use-agent': None,
                            'with-colons': None,
                            'with-fingerprint': None,
                            'fixed-list-mode': None,
                            'list-options': 'show-sig-subpackets,show-uid-validity,show-unusable-uids,show-unusable-subkeys,show-keyring,show-sig-expire',
                            }
                if homedir is not None:
                        self.set_option('homedir', homedir)

        def set_option(self, option, value = None):
                """set an option to pass to gpg

                this adds the given 'option' commandline argument with
                the value 'value'. to pass a flag without an argument,
                use 'None' for value"""
                self.options[option] = value

        def unset_option(self, option):
                """remove an option from the gpg commandline"""
                if option in self.options:
                        del self.options[option]
                else:
                        return false

        def build_command(self, command):
                """internal helper to build a proper gpg commandline

                this will add relevant arguments around the gpg
                binary.

                like the options arguments, the command is expected to
                be a regular gpg command with the -- stripped. the --
                are added before being called. this is to make the
                code more readable, and eventually support other
                backends that actually make more sense.

                this uses build_command to create a commandline out of
                the 'options' dictionnary, and appends the provided
                command at the end. this is because order of certain
                options matter in gpg, where some options (like
                --recv-keys) are expected to be at the end.

                it is here that the options dictionnary is converted
                into a list. the command argument is expected to be a
                list of arguments that can be converted to strings. if
                it is not a list, it is cast into a list."""
                options = []
                for left, right in self.options.iteritems():
                        options += ['--' + left]
                        if right is not None:
                                options += [str(right)]
                if type(command) is str:
                        command = [command]
                if len(command) > 0:
                        command[0] = '--' + command[0]
                return [self.gpg_binary] + options + command

        def call_command(self, command, stdin=None):
                """internal wrapper to call a GPG commandline

                this will call the command generated by
                build_command() and setup a regular pipe to the
                subcommand.

                this assumes that we have the status-fd on stdout and
                command-fd on stdin, but could really be used in any
                other way.

                we pass the stdin argument in the standard input of
                gpg and we keep the output in the stdout and stderr
                array. the exit code is in the returncode variable.
                """
                proc = subprocess.Popen(self.build_command(command), 0, None, subprocess.PIPE, subprocess.PIPE, subprocess.PIPE)
                (self.stdout, self.stderr) = proc.communicate(stdin)
                self.returncode = proc.returncode
                return proc.returncode == 0

        def version(self, type='short'):
                self.call_command(['version'])
                if type is not 'short': raise TypeError('invalid type')
                m = re.search('gpg \(GnuPG\) (\d+.\d+(?:.\d+)*)', self.stdout)
                return m.group(1)

        def import_data(self, data):
                """Import OpenPGP data blocks into the keyring.

                This takes actual OpenPGP data, ascii-armored or not,
                gpg will gladly take it. This can be signatures,
                public, private keys, etc.

                You may need to set import-flags to import
                non-exportable signatures, however.
                """
                self.call_command(['import'], data)
                return self.returncode == 0

        def export_data(self, fpr, secret = False):
                """Export OpenPGP data blocks from the keyring.

                This exports actual OpenPGP data, by default in binary
                format, but can also be exported asci-armored by
                setting the 'armor' option."""
                if secret: command = 'export-secret-keys'
                else: command = 'export'
                self.call_command([command, fpr])
                return self.stdout

        def fetch_keys(self, fpr, keyserver = None):
                """Download keys from a keyserver into the local keyring

                This expects a fingerprint (or a at least a key id).

                Returns true if the command succeeded.
                """
                if keyserver:
                        self.set_option('keyserver', keyserver)
                self.call_command(['recv-keys', fpr])
                return self.returncode == 0

        def get_keys(self, pattern, secret = False, public = True):
                """load keys matching a specific patterns

                this uses the (rather poor) list-keys API to load keys
                information
                """
                keys = {}
                if public:
                        self.call_command(['list-keys', pattern])
                        if self.returncode == 0:
                                key = OpenPGPkey()
                                key.parse_gpg_list(self.stdout)
                                keys[key.fpr] = key
                        elif self.returncode == 2:
                                return None
                        else:
                                raise RuntimeError("unexpected GPG exit code in list-keys: %d" % self.returncode)
                if secret:
                        self.call_command(['list-secret-keys', pattern])
                        if self.returncode == 0:
                                key = OpenPGPkey()
                                key.parse_gpg_list(self.stdout)
                                if key.fpr in keys:
                                        keys[key.fpr].parse_gpg_list(self.stdout)
                                        del key
                                else:
                                        keys[key.fpr] = key
                        elif self.returncode == 2:
                                return None
                        else:
                                raise RuntimeError("unexpected GPG exit code in list-keys: %d" % self.returncode)
                return keys

        def sign_key(self, fpr):
                """sign a key already present in the temporary keyring

                use set_option('local-user', key) to choose a signing key
                """
                return self.call_command(['sign-key', fpr], "y\n")

class GpgTemp(Gpg):
        def __init__(self):
                """Override the parent class to generate a temporary
                GPG home that gets destroyed at the end of
                operations."""

                # Create tempdir for gpg operations
                Gpg.__init__(self, tempfile.mkdtemp(prefix="monkeysign-"))

        def __del__(self):
                shutil.rmtree(self.options['homedir'])

class OpenPGPkey():
        """An OpenPGP key.

        Some of this datastructure is taken verbatim from GPGME.
        """

        # the key has a revocation certificate
        # @todo - not implemented
        revoked = False

        # the expiry date is set and it is passed
        # @todo - not implemented
        expired = False

        # the key has been disabled
        # @todo - not implemented
        disabled = False

        # ?
        invalid = False

        # the various flags on this key
        purpose = {}

        # This is true if the subkey can be used for qualified
        # signatures according to local government regulations.
        # @todo - not implemented
        qualified = False

        # this key has also secret key material
        secret = False

        # This is the public key algorithm supported by this subkey.
        algo = -1

        # This is the length of the subkey (in bits).
        length = None

        # The key fingerprint (a string representation)
        fpr = None

        # The key id (a string representation), only if the fingerprint is unavailable
        # use keyid() instead of this field to find the keyid
        _keyid = None

        # This is the creation timestamp of the subkey.  This is -1 if
        # the timestamp is invalid, and 0 if it is not available.
        creation = 0

        # This is the expiration timestamp of the subkey, or 0 if the
        # subkey does not expire.
        expiry = 0

        # the list of OpenPGPuids associated with this key
        uids = {}

        # the list of subkeys associated with this key
        subkeys = {}

        def __init__(self):
                self.purpose = { 'encrypt': True, # if the public key part can be used to encrypt data
                                 'sign': True,    # if the private key part can be used to sign data
                                 'certify': True, # if the private key part can be used to sign other keys
                                 'authenticate': True, # if this key can be used for authentication purposes
                                 }
                self.uids = {}
                self.subkeys = {}

        def keyid(self, l=8):
                if self.fpr is None:
                        assert(self._keyid is not None)
                        return self._keyid[-l:]
                return self.fpr[-l:]

        def parse_gpg_list(self, text):
                for block in text.split("\n"):
                        record = block.split(":")
                        #for block in record:
                        #        print >>sys.stderr, block, "|\t",
                        #print >>sys.stderr, "\n"
                        rectype = record[0]
                        if rectype == 'tru':
                                (rectype, trust, selflen, algo, keyid, creation, expiry, serial) = record
                        elif rectype == 'fpr':
                                self.fpr = record[9]
                        elif rectype == 'pub':
                                (null, trust, self.length, self.algo, keyid, self.creation, self.expiry, serial, trust, uid, sigclass, purpose, smime) = record
                                for p in self.purpose:
                                        self.purpose[p] = p[0].lower() in purpose.lower()
                        elif rectype == 'uid':
                                (rectype, trust, null  , null, null, creation, expiry, uidhash, null, uid, null) = record
                                self.uids[uidhash] = OpenPGPuid(uid, trust, creation, expiry, uidhash)
                        elif rectype == 'sub':
                                subkey = OpenPGPkey()
                                (rectype, trust, subkey.length, subkey.algo, subkey._keyid, subkey.creation, subkey.expiry, serial, trust, uid, sigclass, purpose, smime) = record
                                for p in subkey.purpose:
                                        subkey.purpose[p] = p[0].lower() in purpose.lower()
                                self.subkeys[subkey._keyid] = subkey
                        elif rectype == 'sec':
                                (null, trust, self.length, self.algo, keyid, self.creation, self.expiry, serial, trust, uid, sigclass, purpose, smime, wtf, wtf, wtf) = record
                                self.secret = True
                        elif rectype == 'ssb':
                                subkey = OpenPGPkey()
                                (rectype, trust, subkey.length, subkey.algo, subkey._keyid, subkey.creation, subkey.expiry, serial, trust, uid, sigclass, purpose, smime, wtf, wtf, wtf) = record
                                if subkey._keyid in self.subkeys:
                                        # XXX: nothing else to add here?
                                        self.subkeys[subkey._keyid].secret = True
                                else:
                                        self.subkeys[subkey._keyid] = subkey
                        elif rectype == '':
                                pass
                        else:
                                raise NotImplementedError("record type '%s' not implemented" % rectype)

        def __str__(self):
                ret = "pub    " + self.length + "R/" 
                ret += self.keyid(8) + " " + self.creation
                if self.expiry: ret += ' [expiry: ' + self.expiry + ']'
                ret += "\n"
                ret += '    Fingerprint = ' + self.fpr + "\n"
                for uid in self.uids.values():
                        ret += "uid      [ " + uid.trust + " ] " + uid.uid + "\n"
                for subkey in self.subkeys.values():
                        ret += "sub   " + subkey.length + "R/" + subkey.keyid(8) + " " + subkey.creation
                        if subkey.expiry: ret += ' [expiry: ' + subkey.expiry + "]"
                        ret += "\n"
                return ret

class OpenPGPuid():
        def __init__(self, uid, trust, creation = 0, expire = None, uidhash = ''):
                self.uid = uid
                self.trust = trust
                self.creation = creation
                self.expire = expire
                self.uidhash = uidhash
