import irc.bot
import irc.strings
import json
import argparse

class Configuration(dict):
    """Data structure representing the configuration for the BootstrapBot.

    The configuration is read in as a json file from a given filepath and 
    represented as a dictionary internally, this class implements __getitem__ and
    __setitem__ so it can be used like a normal dictionary."""
    def __init__(self, filepath):
        super().__init__(self)
        config_file = open(filepath)
        self.update(json.load(config_file))
        config_file.close()
        self._filepath = filepath

    def save(self):
        """Save the in memory configuration to disk."""
        config_file = open(self._filepath)
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
        if event.source.nick == self.config["bot_controller"]:
            try:
                command = getattr(self, "do_" + event.arguments[0])
            except AttributeError:
                print("Recieved invalid command.")
            command()

parser = argparse.ArgumentParser()
parser.add_argument("control_nick")
parser.add_argument("bot_nick")
parser.add_argument("server_address")
parser.add_argument("-p", "--port", default=6667)
arguments = parser.parse_args()
BootstrapBot(arguments.control_nick,
             arguments.bot_nick,
             arguments.server_address,
             arguments.port)
