"""WRAM addresses verified against ~/dev/pokered/ (pokered.sym, wram.asm, event_constants.asm)."""

# wIsInBattle — pokered.sym 00:d057
W_IS_IN_BATTLE = 0xD057

# wPartyCount — pokered.sym 00:d163
W_PARTY_COUNT = 0xD163

# wPartySpecies — pokered.sym 00:d164 (6 slots)
W_PARTY_SPECIES = (0xD164, 0xD165, 0xD166, 0xD167, 0xD168, 0xD169)

# wPartyMon1HP … wPartyMon6HP — pokered.sym 00:d16c, d198, d1c4, d1f0, d21c, d248
W_PARTY_MON_HP = (0xD16C, 0xD198, 0xD1C4, 0xD1F0, 0xD21C, 0xD248)

# wPartyMon1Level … wPartyMon6Level — pokered.sym 00:d18c, d1b8, d1e4, d210, d23c, d268
W_PARTY_MON_LEVEL = (0xD18C, 0xD1B8, 0xD1E4, 0xD210, 0xD23C, 0xD268)

# wPartyMon1MaxHP … wPartyMon6MaxHP — pokered.sym 00:d18d, d1b9, d1e5, d211, d23d, d269
W_PARTY_MON_MAX_HP = (0xD18D, 0xD1B9, 0xD1E5, 0xD211, 0xD23D, 0xD269)

# wPlayerMoney — pokered.sym 00:d347 (not read by env core; included per spec D18)
W_PLAYER_MONEY = 0xD347

# wObtainedBadges — pokered.sym 00:d356
W_OBTAINED_BADGES = 0xD356

# wCurMap — pokered.sym 00:d35e
W_CUR_MAP = 0xD35E

# wYCoord — pokered.sym 00:d361
W_Y_COORD = 0xD361

# wXCoord — pokered.sym 00:d362
W_X_COORD = 0xD362

# wEventFlags — pokered.sym 00:d747; NUM_EVENTS=$A00 in event_constants.asm
W_EVENT_FLAGS_START = 0xD747
# Last event-flag byte before wGrassRate at 0xD887 (pokered.sym 00:d887)
W_EVENT_FLAGS_END_INCLUSIVE = 0xD886
# v2 reward / logging scan bound (exclusive end for range())
W_EVENT_FLAGS_END_EXCLUSIVE_V2 = 0xD87E

EVENT_FLAG_BYTES_OBS = W_EVENT_FLAGS_END_INCLUSIVE - W_EVENT_FLAGS_START + 1  # 320
EVENT_FLAG_BITS_OBS = EVENT_FLAG_BYTES_OBS * 8  # 2560

# EVENT_BOUGHT_MUSEUM_TICKET — event_constants.asm const $68 → byte 13 bit 0 → 0xD754
EVENT_BOUGHT_MUSEUM_TICKET = (0xD754, 0)

# wEnemyMon1Level … wEnemyMon6Level — pokered.sym 00:d8c5, d8f1, d91d, d949, d975, d9a1
W_ENEMY_MON_LEVEL = (0xD8C5, 0xD8F1, 0xD91D, 0xD949, 0xD975, 0xD9A1)
