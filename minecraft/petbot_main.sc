__config() -> {
    'scope' -> 'global',
    'allow_command_conflicts' -> true,
    'commands' -> {
        'setup' -> _() -> (_setup_bot()),
        'start' -> _() -> (_start_polling()),
        'stop'  -> _() -> (global_poll_running = false; print('[PetBot] Stopped.')),
        'status'-> _() -> (_print_status())
    }
};

__on_start() -> (
    global_BOT_NAME      = 'PetBot';
    global_POLL_TICKS    = 10;
    global_poll_running  = false;
    global_context_ticks = 0;
    // ── SKIN: paste your textures.minecraft.net/texture/<hash> URL here ──
    // Leave empty string '' to skip skin setting
    global_BOT_SKIN      = 'https://textures.minecraft.net/texture/ff208148ec1b4bb02a96dcfd17e581ad47f1124081f389e79fafe69d5b81fa10';
);

_setup_bot() -> (
    caller = player();
    p = pos(caller);
    cmd = str('player %s spawn at %d %d %d', global_BOT_NAME, floor(p:0), floor(p:1), floor(p:2));
    run(cmd);
    print('[PetBot] Spawning...');
    schedule(20, _() -> _finish_setup());
);

_finish_setup() -> (
    bot = player(global_BOT_NAME);
    if(!bot,
        print('[PetBot] ERROR: bot did not spawn — check /carpet fakePlayers true');
        return(false)
    );
    _start_polling();
    print('[PetBot] Setup complete! Bridge: http://127.0.0.1:5050');

    // Apply skin if configured in global_BOT_SKIN
    if(global_BOT_SKIN != '',
        run(str('player %s skin set %s', global_BOT_NAME, global_BOT_SKIN));
        print('[PetBot] Skin applied.')
    );
    run('tellraw @a [{"text":"<PetBot> ","color":"yellow","bold":true},{"text":"PetBot online and ready!","color":"white"}]');
);

_print_status() -> (
    resp = try(http_request({
        'uri'    -> 'http://127.0.0.1:5050/health',
        'method' -> 'GET'
    }), e -> null);
    if(resp,
        print(str('[PetBot] Bridge OK - %s', resp:'body')),
        print('[PetBot] Bridge unreachable.')
    );
    print(str('[PetBot] Polling: %s', global_poll_running));
    print(str('[PetBot] Bot online: %s', player(global_BOT_NAME) != null));
);

_start_polling() -> (
    if(global_poll_running, print('[PetBot] Already polling.'); return(false));
    global_poll_running = true;
    print(str('[PetBot] Polling every %d ticks.', global_POLL_TICKS));
    schedule(global_POLL_TICKS, _() -> _poll_tick());
);

_poll_tick() -> (
    if(!global_poll_running, return());
    _fetch_and_execute();
    global_context_ticks = global_context_ticks + 1;
    if(global_context_ticks >= 4,
        global_context_ticks = 0;
        _push_context()
    );
    schedule(global_POLL_TICKS, _() -> _poll_tick());
);

// Forward player chat to Python so the agent can respond
__on_player_message(player, message) -> (
    // Ignore PetBot talking to itself
    if(str('%s', player) == global_BOT_NAME, return());
    try(
        http_request({
            'uri'     -> 'http://127.0.0.1:5050/chat',
            'method'  -> 'POST',
            'headers' -> {'Content-Type' -> 'application/json'},
            'body'    -> encode_json({'player' -> str('%s', player), 'message' -> str('%s', message)})
        }),
        e -> null   // swallow http errors silently
    );
);

_push_context() -> (
    bot = player(global_BOT_NAME);
    if(!bot, return());
    p  = pos(bot);
    bx = floor(p:0);
    by = floor(p:1);
    bz = floor(p:2);
    nearby = [];
    for(range(-2, 3),
        dx = _;
        for(range(-2, 3),
            nearby += [str('%d,%d:%s', dx, _, block(bx+dx, by-1, bz+_))]
        )
    );
    holds = query(bot, 'holds');
    held  = if(holds, str('%s', holds:0), 'empty');
    ctx = {
        'pos'           -> [bx, by, bz],
        'yaw'           -> query(bot, 'yaw'),
        'pitch'         -> query(bot, 'pitch'),
        'selected_slot' -> query(bot, 'selected_slot'),
        'held_main'     -> held,
        'block_below'   -> str('%s', block(bx, by-1, bz)),
        'block_north'   -> str('%s', block(bx, by, bz-1)),
        'block_south'   -> str('%s', block(bx, by, bz+1)),
        'block_east'    -> str('%s', block(bx+1, by, bz)),
        'block_west'    -> str('%s', block(bx-1, by, bz)),
        'nearby_floor'  -> nearby
    };
    try(http_request({
        'uri'     -> 'http://127.0.0.1:5050/context',
        'method'  -> 'POST',
        'headers' -> {'Content-Type' -> 'application/json'},
        'body'    -> encode_json(ctx)
    }), e -> null);
);

_fetch_and_execute() -> (
    resp = try(http_request({
        'uri'     -> 'http://127.0.0.1:5050/commands',
        'method'  -> 'GET',
        'headers' -> {'Accept' -> 'application/json'}
    }), e -> null);
    if(!resp, return());
    if(resp:'status_code' != 200, return());
    cmds = decode_json(resp:'body');
    if(!cmds || length(cmds) == 0, return());
    results = [];
    for(cmds, results += [_dispatch(_)]);
    try(http_request({
        'uri'     -> 'http://127.0.0.1:5050/results',
        'method'  -> 'POST',
        'headers' -> {'Content-Type' -> 'application/json'},
        'body'    -> encode_json(results)
    }), e -> null);
);

_dispatch(cmd) -> (
    id     = cmd:'id';
    action = cmd:'action';
    result = if(action == 'move',        _do_move(cmd),
             if(action == 'stop',        _do_stop(cmd),
             if(action == 'hotbar',      _do_hotbar(cmd),
             if(action == 'jump',        _do_jump(cmd),
             if(action == 'sneak',       _do_sneak(cmd),
             if(action == 'sprint',      _do_sprint(cmd),
             if(action == 'look',        _do_look(cmd),
             if(action == 'turn',        _do_turn(cmd),
             if(action == 'use',         _do_use(cmd),
             if(action == 'attack',      _do_attack(cmd),
             if(action == 'drop',        _do_drop(cmd),
             if(action == 'sit',         _do_sit(cmd),
             if(action == 'chat',        _do_chat(cmd),
             if(action == 'mine',        _do_mine(cmd),
             if(action == 'place',       _do_place(cmd),
             if(action == 'interact',    _do_interact(cmd),
             if(action == 'raw_command', _do_raw(cmd),
             {'ok' -> false, 'error' -> str('unknown action: %s', action)}
             )))))))))))))))));
    {'id' -> id} + result
);

_do_move(cmd) -> (
    bot = player(global_BOT_NAME);
    if(!bot, return({'ok' -> false, 'error' -> 'bot offline'}));
    dir = cmd:'direction';
    // Normalise 'back' -> 'backward' in case LLM uses it
    if(dir == 'back', dir = 'backward');
    run(str('player %s move %s', global_BOT_NAME, dir));
    {'ok' -> true}
);

_do_stop(cmd) -> (
    run(str('player %s stop', global_BOT_NAME));
    {'ok' -> true}
);

_do_hotbar(cmd) -> (
    // Carpet command: player <name> hotbar <slot 1-9>
    // Scarpet slot is 0-8 from Python; Carpet hotbar is 1-9
    slot = cmd:'slot' + 1;
    run(str('player %s hotbar %d', global_BOT_NAME, slot));
    {'ok' -> true}
);

_do_jump(cmd) -> (
    run(str('player %s jump once', global_BOT_NAME));
    {'ok' -> true}
);

_do_sneak(cmd) -> (
    action = if(cmd:'enable', 'sneak', 'unsneak');
    run(str('player %s %s', global_BOT_NAME, action));
    {'ok' -> true}
);

_do_sprint(cmd) -> (
    action = if(cmd:'enable', 'sprint', 'unsprint');
    run(str('player %s %s', global_BOT_NAME, action));
    {'ok' -> true}
);

_do_look(cmd) -> (
    if(cmd:'direction',
        run(str('player %s look %s', global_BOT_NAME, cmd:'direction')),
        run(str('player %s look %s %s', global_BOT_NAME, cmd:'yaw', cmd:'pitch'))
    );
    {'ok' -> true}
);

_do_turn(cmd) -> (
    run(str('player %s turn %s', global_BOT_NAME, cmd:'direction'));
    {'ok' -> true}
);

_do_use(cmd) -> (
    mode = if(cmd:'mode', cmd:'mode', 'once');
    run(str('player %s use %s', global_BOT_NAME, mode));
    {'ok' -> true}
);

_do_attack(cmd) -> (
    mode = if(cmd:'mode', cmd:'mode', 'once');
    run(str('player %s attack %s', global_BOT_NAME, mode));
    {'ok' -> true}
);

_do_drop(cmd) -> (
    what = if(cmd:'what', cmd:'what', 'mainhand');
    run(str('player %s drop %s', global_BOT_NAME, what));
    {'ok' -> true}
);

_do_sit(cmd) -> (
    // JustSit: look straight down then right-click
    run(str('player %s look down', global_BOT_NAME));
    schedule(2, _() -> run(str('player %s use once', global_BOT_NAME)));
    {'ok' -> true}
);

// Use tellraw (always works) + player chat command (works in some Carpet versions)
_do_chat(cmd) -> (
    bot = player(global_BOT_NAME);
    if(!bot, return({'ok' -> false, 'error' -> 'bot offline'}));
    msg = cmd:'message';
    // tellraw @a guaranteed to show in chat — formatted to look like player chat
    run(str('tellraw @a [{"text":"<PetBot> ","color":"yellow","bold":true},{"text":"%s","color":"white"}]', msg));
    {'ok' -> true}
);

_do_mine(cmd) -> (
    run(str('setblock %d %d %d air destroy', cmd:'x', cmd:'y', cmd:'z'));
    {'ok' -> true}
);

_do_place(cmd) -> (
    run(str('setblock %d %d %d %s', cmd:'x', cmd:'y', cmd:'z', cmd:'block_type'));
    {'ok' -> true}
);

_do_interact(cmd) -> (
    run(str('player %s use block %d %d %d', global_BOT_NAME, cmd:'x', cmd:'y', cmd:'z'));
    {'ok' -> true}
);

_do_raw(cmd) -> (
    result = run(cmd:'command');
    {'ok' -> true, 'data' -> str('%s', result)}
);