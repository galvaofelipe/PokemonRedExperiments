from frozen.ram_map import W_PARTY_COUNT


class NullReward:
    """Zero training reward for frozen eval episodes (D1)."""

    def reset(self, env):
        self.died_count = 0
        self.total_healing_rew = 0
        self.party_size = 0
        self.last_health = 1.0
        self.progress_reward = {
            "event": 0.0,
            "heal": 0.0,
            "badge": 0.0,
            "explore": 0.0,
            "stuck": 0.0,
        }
        self.total_reward = 0.0

    def update_heal(self, env):
        cur_health = env.read_hp_fraction()
        if cur_health > self.last_health and env.read_m(W_PARTY_COUNT) == self.party_size:
            if self.last_health <= 0:
                self.died_count += 1

    def update(self, env):
        return 0.0

    def group_rewards(self, env):
        return (0.0, 0.0, 0.0)
