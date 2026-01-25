# personalityEngine.py - UPGRADED VERSION
"""
Multi-dimensional mood system with emotional decay and context awareness
"""

import random
import time
import json
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class EmotionalState:
    """Tracks multiple emotional dimensions simultaneously"""
    # Core emotions (0-100 scale)
    smugness: float = 50.0  # Default personality trait
    curiosity: float = 30.0  # Interest in new things
    boredom: float = 0.0  # Lack of stimulation
    affection: float = 20.0  # Relationship with user
    annoyance: float = 0.0  # Frustration level
    energy: float = 80.0  # Tiredness/alertness

    # Metadata
    last_update: float = 0.0
    last_interaction: float = 0.0

    def decay(self, delta_time: float):
        """Emotions naturally return to baseline over time"""
        decay_rate = 0.1  # How fast emotions fade (per second)

        # Curiosity fades quickly
        self.curiosity = max(30.0, self.curiosity - (decay_rate * delta_time * 2))

        # Annoyance fades slowly (pet holds grudges lol)
        self.annoyance = max(0.0, self.annoyance - (decay_rate * delta_time * 0.5))

        # Boredom increases when ignored
        time_since_interaction = time.time() - self.last_interaction
        if time_since_interaction > 60:  # 1 min of being ignored
            self.boredom = min(100.0, self.boredom + (decay_rate * delta_time))
        else:
            self.boredom = max(0.0, self.boredom - (decay_rate * delta_time))

        # Energy decreases over time (gets sleepy)
        self.energy = max(0.0, self.energy - (decay_rate * delta_time * 0.3))

        self.last_update = time.time()


class AdvancedPersonality:
    def __init__(self, pet_instance, gui_instance, mood_lines):
        self.pet = pet_instance
        self.gui = gui_instance
        self.mood_lines = mood_lines

        # Multi-dimensional emotional state
        self.emotions = EmotionalState()

        # Conversation history (prevents repetition)
        self.recent_comments = []  # Last 10 things said
        self.app_comment_cooldowns = {}  # App -> last comment time

        # Personality traits (affects how emotions translate to behavior)
        self.traits = {
            'snarkiness': 0.8,  # How sassy (0-1)
            'chattiness': 0.5,  # How often to talk (0-1)
            'patience': 0.3,  # Tolerance for repetition (0-1)
            'playfulness': 0.6  # Likelihood of random actions (0-1)
        }

        self.isTalking = False
        self.lastTalkTime = time.time()

    def update(self):
        """Called every frame - updates emotional state"""
        now = time.time()
        delta_time = now - self.emotions.last_update

        # Natural emotional decay
        self.emotions.decay(delta_time)

        # React to pet's ML findings
        self._process_pet_state()

        # Decide if we should talk
        if self._should_talk():
            self.randomTalk()

    def _process_pet_state(self):
        """Update emotions based on what the pet detected"""
        # Surprised = unusual duration
        if self.pet.surprised:
            self.emotions.curiosity = min(100.0, self.emotions.curiosity + 20)
            self.emotions.energy = min(100.0, self.emotions.energy + 10)

        # Curious = unusual timing
        if self.pet.curious:
            self.emotions.curiosity = min(100.0, self.emotions.curiosity + 30)
            self.emotions.boredom = max(0.0, self.emotions.boredom - 20)

        # Detect repetitive app usage
        category = self.pet.categorize(self.pet.activeApp) if self.pet.activeApp else None
        if category:
            # Check if user keeps doing the same thing
            if self._is_repetitive_behavior():
                self.emotions.smugness = min(100.0, self.emotions.smugness + 5)
                self.emotions.boredom = min(100.0, self.emotions.boredom + 10)

    def _is_repetitive_behavior(self) -> bool:
        """Check if user is stuck in a pattern"""
        if len(self.pet.chatHistory) < 5:
            return False

        # Last 5 sessions
        recent = self.pet.chatHistory[-5:]
        categories = [r['category'] for r in recent]

        # If 4/5 are the same category = repetitive
        most_common = max(set(categories), key=categories.count)
        return categories.count(most_common) >= 4

    def _should_talk(self) -> bool:
        """Decide if the pet should say something"""
        now = time.time()

        # Minimum cooldown (don't spam)
        if now - self.lastTalkTime < 6:
            return False

        # High boredom = more likely to talk
        if self.emotions.boredom > 70:
            return random.random() < 0.3  # 30% chance when bored

        # High curiosity = eager to comment
        if self.emotions.curiosity > 60:
            return random.random() < 0.5  # 50% chance when curious

        # Normal chattiness
        base_chance = self.traits['chattiness'] * 0.1  # 5% base chance
        return random.random() < base_chance

    def getDominantMood(self) -> str:
        """Determine which mood is strongest right now"""
        e = self.emotions

        # Boredom overrides everything when high
        if e.boredom > 60:
            return "bored"

        # Curiosity is strong
        if e.curiosity > 50:
            return "curious"

        # Surprised is temporary but impactful
        if self.pet.surprised and e.curiosity > 40:
            return "surprised"

        # Default smugness
        if e.smugness > 40:
            return "smug"

        return "smug"  # Fallback

    def randomTalk(self):
        """Generate contextual dialogue based on emotional state"""
        mood = self.getDominantMood()
        category = self.pet.categorize(self.pet.activeApp) if self.pet.activeApp else "unknown"

        # Get available lines for this mood
        available_lines = self.mood_lines.get(mood, ["..."])

        # Filter out recently used lines (prevent repetition)
        fresh_lines = [l for l in available_lines if l not in self.recent_comments]
        if not fresh_lines:  # Used everything, reset
            fresh_lines = available_lines
            self.recent_comments.clear()

        # Pick a line and format it
        line = random.choice(fresh_lines)
        formatted = line.format(
            appName=self.pet.activeApp or "Nothing",
            category=category
        )

        # Remember this comment
        self.recent_comments.append(line)
        if len(self.recent_comments) > 10:
            self.recent_comments.pop(0)

        # Deliver the line
        self.talk(formatted)

    def talk(self, line):
        """Display dialogue to user"""
        self.isTalking = True
        self.gui.showChat(line)
        self.lastTalkTime = time.time()
        self.emotions.last_interaction = time.time()
        self.isTalking = False

    def on_user_click(self):
        """User clicked the pet - adjust emotions"""
        self.emotions.affection = min(100.0, self.emotions.affection + 5)
        self.emotions.boredom = max(0.0, self.emotions.boredom - 20)
        self.emotions.energy = min(100.0, self.emotions.energy + 10)
        self.emotions.last_interaction = time.time()

    def on_user_spam_click(self):
        """User is clicking too much - get annoyed!"""
        self.emotions.annoyance = min(100.0, self.emotions.annoyance + 30)
        self.emotions.affection = max(0.0, self.emotions.affection - 10)


        annoyed_lines = [
            "okay chill out.",
            "dude, relax.",
            "what are you doing??",
            "STOP THAT.",
            "you're annoying me."
        ]
        self.talk(random.choice(annoyed_lines))
        self.emotions.last_interaction = time.time()

    def get_debug_info(self) -> Dict:
        """For debugging - show current emotional state"""
        return {
            'mood': self.getDominantMood(),
            'smugness': round(self.emotions.smugness, 1),
            'curiosity': round(self.emotions.curiosity, 1),
            'boredom': round(self.emotions.boredom, 1),
            'affection': round(self.emotions.affection, 1),
            'annoyance': round(self.emotions.annoyance, 1),
            'energy': round(self.emotions.energy, 1)
        }

