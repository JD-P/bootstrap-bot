import irc.bot
import irc.strings
from irc.client import is_channel
import time
import json
import argparse

class Configuration(dict):
    """Data structure representing the configuration for the BootstrapBot.

    The configuration is read in as a json file from a given filepath and 
    represented as a dictionary internally, this class implements __getitem__ and
    __setitem__ so it can be used like a normal dictionary."""
    def __init__(self, filepath):
        super().__init__(self)
        try:
            config_file = open(filepath)
        except FileNotFoundError:
            self.save(filepath)
            config_file = open(filepath)
        self.update(json.load(config_file))
        config_file.close()
        self._filepath = filepath
        for key in self.keys():
            if key[0] == '#':
                temp_r = Registrar(None, None, None)
                temp_r.update(self[key])
                self[key] = temp_r

    def save(self, filepath=None):
        """Save the in memory configuration to disk."""
        if filepath:
            config_file = open(filepath, 'w')
        else:
            config_file = open(self._filepath, 'w')
        json.dump(self, config_file)
        config_file.close()
        
class BootstrapBot(irc.bot.SingleServerIRCBot):
    """Bootstrap Bot sits in a new channel and waits for others to join. Once they
    join it sends them a notice that they can register with BootstrapBot to express
    interest in the channel. At a certain number of other people expressing interest
    it will send them all an invitation to join the channel. Once a threshold of 
    joins has been reached the bot leaves the channel and lets it grow on its own."""
    def __init__(self, control_nick, nickname, server, port=6667):
        irc.bot.SingleServerIRCBot.__init__(self, [(server, port)], nickname, nickname)
        self._controller = control_nick
        self.config = Configuration('config.json')
        self.config["bot_controller"] = self._controller
        self.config.save()
        
    def on_nicknameinuse(self, connection, event):
        """Append an underscore to the bots nickname if it's already taken."""
        connection.nick(connection.get_nickname() + "_")
        
    def on_privmsg(self, connection, event):
        """Recieve a command over private messaging, if the source of the message
        is the bot controller execute commands otherwise do nothing."""
        if event.source.nick == self.config["bot_controller"]:
            try:
                command = getattr(self, "do_" + event.arguments[0].split()[0])
            except AttributeError:
                print("Recieved invalid command.", event)
                return False
            command(connection, event)

    def do_join(self, connection, event):
        """Join a channel target given by the bot controller."""
        arguments = event.arguments[0].split()
        usage_msg = ["Usage: join <channel name> <invite_threshold> <part_threshold>",
                     "Example: join #test 15 12"]
        try:
            if is_channel(arguments[1]):
                connection.join(arguments[1])
        except IndexError:
            for line in usage_msg:
                connection.notice(event.source.nick, line)
        try:
            if arguments[1] not in self.config and is_channel(arguments[1]):
                self.config[arguments[1]] = Registrar(arguments[1],
                                                      int(arguments[2]),
                                                      int(arguments[3]))
                self.config.save()
        except IndexError:
            for line in usage_msg:
                connection.notice(event.source.nick, line)
        connection.names(arguments[1])

    def do_part(self, connection, event):
        """Part a channel target given by the bot controller."""
        arguments = event.arguments[0].split()
        try:
            if is_channel(arguments[1]):
                connection.part(arguments[1])
        except IndexError:
            pass

    def do_clear(self, connection, event):
        """Clear a given channels nicklist."""
        arguments = event.arguments[0].split()
        usage_msg = "Usage: clear <channel name> Example: clear #test"
        try:
            self.config[arguments[1]].clear()
        except IndexError:
            connection.notice(event.source.nick, usage_msg)
            
    def do_test(self, connection, event):
        """Test command to send the bot controller a message."""
        print("Test command ran!")
        try:
            connection.privmsg(event.source.nick, "Testing.")
        except:
            print("Wrong arguments.")

    def on_pubmsg(self, connection, event):
        """Parse public messages for commands, if a command is found execute it."""
        arguments = event.arguments[0].split()
        try:
            if hasattr(self, "do_pub_" + arguments[0]):
                command = getattr(self, "do_pub_" + arguments[0])
            elif (hasattr(self, "do_pub_" + arguments[1])
                  and arguments[0].strip(":") == connection.get_nickname()):
                command = getattr(self, "do_pub_" + arguments[1])
            else:
                return False
            command(connection, event)
        except IndexError:
            pass

    def do_pub_register(self, connection, event):
        """Register oneself with the bootstrap bot as being interested in a 
        particular channel. The bot sits in a channel and waits for users to 
        register with it. Once a certain threshold of registrations has been 
        reached the bot invites everybody on the registration list."""
        if self.config[event.target].add_nick(event.source.nick):
            if self.config[event.target].invite_threshold_exceeded():
                self.mass_invite(connection, event, self.config[event.target])
            else:
                self.config.save()
        else:
            connection.notice(event.source.nick, "You've already registered.")
            
    def mass_invite(self, connection, event, registrar):
        """Do a mass invite of all the people who have registered their interest
        in a channel."""
        print("Mass invite sending!")
        connection.invite("patrickrobotham", event.target)
        for nick in registrar["registrar"]:
            connection.invite(nick, event.target)
            time.sleep(1)

    def do_pub_list(self, connection, event):
        """Send the list of users who have registered their interest in the channel
        as a notice to user sending the command."""
        registrar = self.config[event.target]
        users = registrar.list()
        msg_header = (str(len(users)) + " of " + str(registrar["invite_threshold"])
                      + " users have registered interest in " + event.target + ":")
        connection.notice(event.source.nick, msg_header)
        for nick in users:
            connection.notice(event.source.nick, nick)
            
    def on_join(self, connection, event):
        """Determine if the channel has passed the part threshold at which the bot
        should leave."""
        try:
            if (len(self.channels[event.target].users()) >
                self.config[event.target]["part_threshold"]):
                connection.part(event.target)
            else:
                welcome_msg = ["Welcome to " + event.target + ", to register your",
                               "interest in this channel, type the word 'register'",
                               "and you will be invited back later once " +
                               str(self.config[event.target]["invite_threshold"]) +
                               " other people have registered as well.", "Type 'help'"
                               " into the channel for a command listing."]
                for line in welcome_msg:
                    connection.notice(event.source.nick, line) 
        except KeyError:
            pass
        
class Registrar(dict):
    """Data structure containing a channels registered interested users, how many
    registrations are needed before sending a mass-invite, and how many users need
    to join the channel before the bot leaves it."""
    def __init__(self, channel, invite_threshold, part_threshold):
        self["channel"] = channel
        self["invite_threshold"] = invite_threshold
        self["part_threshold"] = part_threshold
        self["registrar"] = []

    def add_nick(self, nick):
        """Add a nickname to the interested users list."""
        if nick in self["registrar"]:
            return False
        else:
            self["registrar"].append(nick)
            return True

    def invite_threshold_exceeded(self):
        """Returns true if the invite threshold has been exceeded, returns false
        otherwise."""
        if len(self["registrar"]) >= self["invite_threshold"]:
            return True
        else:
            return False

    def list(self):
        """Return the registrar list of users interested in the channel."""
        return self["registrar"]
        
    def clear(self):
        """Clear the nick list for the channel."""
        self["registrar"] = []
        
parser = argparse.ArgumentParser()
parser.add_argument("control_nick")
parser.add_argument("bot_nick")
parser.add_argument("server_address")
parser.add_argument("-p", "--port", default=6667)
arguments = parser.parse_args()
bot = BootstrapBot(arguments.control_nick,
                   arguments.bot_nick,
                   arguments.server_address,
                   arguments.port)
bot.start()
