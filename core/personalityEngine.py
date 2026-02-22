import random
import time

class PersonalityTraits:
    def __init__(self):
        self.curiosity = random.randint(40, 70)
        self.boredom = random.randint(0, 30)
        self.aggression = random.randint(10, 30)  # How likely to punch
        self.affection = random.randint(30, 70)   # Follows player, looks at you, etc.

    def update(self, context):
        # Increase boredom if idle, decrease if moving/interacting
        if context.get("idle", False):
            self.boredom += random.randint(1, 5)
        else:
            self.boredom = max(0, self.boredom - random.randint(1, 3))
        # Slight random change for realism
        self.curiosity += random.randint(-2, 2)
        self.aggression += random.randint(-1, 1)
        self.affection += random.randint(-1, 1)

class PersonalityEngine:
    def __init__(self, agent, gui, mood_lines):
        self.traits = PersonalityTraits()
        self.agent = agent
        self.gui = gui
        self.mood_lines = mood_lines
        self.isTalking = False
        self.last_act_time = time.time()

    def random_act(self, context):
        # Decide action based on personality, context
        self.traits.update(context)
        action = None

        # Boredom triggers: walk, look around, emote, punch the air/player
        if self.traits.boredom > 60 and random.random() < 0.3:
            action = "wander"
        elif self.traits.curiosity > 60 and random.random() < 0.2:
            action = "look_at_player"
        elif self.traits.aggression > 50 and random.random() < 0.15:
            action = "punch_player"
        elif self.traits.affection > 60 and random.random() < 0.15:
            action = "follow_player"
        else:
            action = "idle"

        return action

    def act(self, context, scarpet_bridge):
        # Every few seconds, decide something to do
        now = time.time()
        if now - self.last_act_time > random.randint(2, 6):
            action = self.random_act(context)
            self.last_act_time = now
            # You can expand these with more personality!
            if action == "wander":
                scarpet_bridge.send_scarpet_command('petbot_wander()')
            elif action == "look_at_player":
                scarpet_bridge.send_scarpet_command('petbot_look_at_player()')
            elif action == "punch_player":
                scarpet_bridge.send_scarpet_command('petbot_punch_player()')
            elif action == "follow_player":
                scarpet_bridge.send_scarpet_command('petbot_follow_player()')
            else:
                # Do nothing or idle animation
                pass