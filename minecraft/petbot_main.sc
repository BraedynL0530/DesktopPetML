// scarplet/petbot_main.sc
// ============================================================
// PetBot — Main Scarplet script
//
// Install:
//   1. Copy this file to <server>/scripts/petbot_main.sc
//   2. /script load petbot_main
//   3. /petbot setup          <- run once to spawn bot + start polling
//
// Requires: Carpet mod (≥1.4.112) with Scarplet enabled
//           Python bridge running on BRIDGE_HOST:BRIDGE_PORT
// ============================================================

// ---------- Configuration ----------
global BRIDGE_HOST  = '127.0.0.1';
global BRIDGE_PORT  = 5050;
global BOT_NAME     = 'PetBot';
global POLL_TICKS   = 10;   // poll every 10 game ticks (~0.5 s)
global SKIN_URL     = '';   // set by /petbot setup or /petbot skin <url>

// ---------- Internal state ----------
global _poll_running = false;
global _tick_counter = 0;

// ============================================================
// /petbot  command tree
// ============================================================

__command() -> 'petbot';

petbot() -> (
    print('Usage: /petbot <setup|start|stop|skin|status>');
);

// /petbot setup [skin_url]
petbot_setup(skin_url) -> (
    _setup_bot(skin_url);
);
petbot_setup() -> (
    _setup_bot('');
);

// /petbot start
petbot_start() -> (
    _start_polling();
);

// /petbot stop
petbot_stop() -> (
    global _poll_running = false;
    print('[PetBot] Polling stopped.');
);

// /petbot skin <url>
petbot_skin(url) -> (
    global SKIN_URL = url;
    _apply_skin(BOT_NAME, url);
);

// /petbot status
petbot_status() -> (
    bridge_url = str('http://', BRIDGE_HOST, ':', BRIDGE_PORT, '/health');
    resp = http_request(bridge_url, 'GET', {}, null);
    if(resp,
        print(str('[PetBot] Bridge: ', resp:body)),
        print('[PetBot] Bridge unreachable.')
    );
    print(str('[PetBot] Polling: ', _poll_running));
    print(str('[PetBot] Bot online: ', player(BOT_NAME) != null));
);

// ============================================================
// Setup helper — spawns bot, sets skin, starts polling
// ============================================================

_setup_bot(skin_url) -> (
    // 1. Spawn fake player at caller's location
    caller = player();
    pos    = pos(caller);
    px = pos:0; py = pos:1; pz = pos:2;

    print(str('[PetBot] Spawning ', BOT_NAME, ' at ', px, ' ', py, ' ', pz));
    run(str('player ', BOT_NAME, ' spawn at ', px, ' ', py, ' ', pz, ' in ', dimension(caller)));

    // 2. Short wait for player to fully spawn
    schedule(20, 'game', '_finish_setup', skin_url);
);

_finish_setup(skin_url) -> (
    bot = player(BOT_NAME);
    if(!bot,
        print('[PetBot] ERROR: bot did not spawn. Check Carpet is installed and /carpet fakePlayerNamePrefix is set correctly.');
        return(false);
    );

    // 3. Apply skin if provided
    if(skin_url != '',
        global SKIN_URL = skin_url;
        _apply_skin(BOT_NAME, skin_url);
    );

    // 4. Start polling loop
    _start_polling();
    print('[PetBot] Setup complete! Bridge: http://' + BRIDGE_HOST + ':' + str(BRIDGE_PORT));
);

// ============================================================
// Skin helper
// ============================================================

_apply_skin(bot_name, url) -> (
    if(url == '', return(false));
    // Carpet command: player <name> skin set <url>
    run(str('player ', bot_name, ' skin set ', url));
    print(str('[PetBot] Skin applied: ', url));
    true
);

// ============================================================
// Polling loop (scheduled task)
// ============================================================

_start_polling() -> (
    if(_poll_running,
        print('[PetBot] Already polling.');
        return(false);
    );
    global _poll_running = true;
    print(str('[PetBot] Starting poll loop every ', POLL_TICKS, ' ticks.'));
    schedule(POLL_TICKS, 'game', '_poll_tick');
);

_poll_tick() -> (
    if(!_poll_running, return());       // stopped externally

    _fetch_and_execute();

    schedule(POLL_TICKS, 'game', '_poll_tick');  // reschedule
);

// ============================================================
// Fetch commands from bridge and execute
// ============================================================

_fetch_and_execute() -> (
    url  = str('http://', BRIDGE_HOST, ':', BRIDGE_PORT, '/commands');
    resp = http_request(url, 'GET', {'Accept': 'application/json'}, null);

    if(!resp || resp:code != 200,
        // Bridge not reachable yet — silently skip
        return();
    );

    cmds = decode_json(resp:body);
    if(!cmds || length(cmds) == 0, return());

    results = [];
    for(cmds, cmd,
        result = _dispatch(cmd);
        results += [result];
    );

    // POST results back
    result_url = str('http://', BRIDGE_HOST, ':', BRIDGE_PORT, '/results');
    http_request(result_url, 'POST',
        {'Content-Type': 'application/json'},
        encode_json(results)
    );
);

// ============================================================
// Action dispatcher
// ============================================================

_dispatch(cmd) -> (
    id     = cmd:'id';
    action = cmd:'action';

    result = if(action == 'move',          _do_move(cmd),
             if(action == 'mine',          _do_mine(cmd),
             if(action == 'place',         _do_place(cmd),
             if(action == 'interact',      _do_interact(cmd),
             if(action == 'sit',           _do_sit(cmd),
             if(action == 'place_furniture', _do_place_furniture(cmd),
             if(action == 'trinket',       _do_trinket(cmd),
             if(action == 'jei_search',    _do_jei_search(cmd),
             if(action == 'spawn_player',  _do_spawn_player(cmd),
             if(action == 'set_skin',      _do_set_skin(cmd),
             if(action == 'run_script',    _do_run_script(cmd),
             if(action == 'player_action', _do_player_action(cmd),
             if(action == 'raw_command',   _do_raw_command(cmd),
             {'ok': false, 'error': str('unknown action: ', action)}
             )))))))))))));

    {'id': id} + result
);

// ============================================================
// Action implementations
// ============================================================

_do_move(cmd) -> (
    dir  = cmd:'direction';
    dist = cmd:'distance';
    bot  = player(BOT_NAME);
    if(!bot, return({'ok': false, 'error': 'bot offline'}));

    p = pos(bot);
    new_pos = if(dir == 'forward',  [p:0,        p:1, p:2 + dist],
              if(dir == 'back',     [p:0,        p:1, p:2 - dist],
              if(dir == 'right',    [p:0 + dist, p:1, p:2       ],
              if(dir == 'left',     [p:0 - dist, p:1, p:2       ],
              if(dir == 'up',       [p:0, p:1 + dist, p:2       ],
              if(dir == 'down',     [p:0, p:1 - dist, p:2       ],
              null))))));

    if(!new_pos, return({'ok': false, 'error': str('unknown direction: ', dir)}));

    run(str('player ', BOT_NAME, ' move ', dir));
    {'ok': true}
);

_do_mine(cmd) -> (
    x = cmd:'x'; y = cmd:'y'; z = cmd:'z';
    run(str('setblock ', x, ' ', y, ' ', z, ' air destroy'));
    {'ok': true}
);

_do_place(cmd) -> (
    x = cmd:'x'; y = cmd:'y'; z = cmd:'z';
    bt = cmd:'block_type';
    run(str('setblock ', x, ' ', y, ' ', z, ' ', bt));
    {'ok': true}
);

_do_interact(cmd) -> (
    x = cmd:'x'; y = cmd:'y'; z = cmd:'z';
    run(str('player ', BOT_NAME, ' use block ', x, ' ', y, ' ', z));
    {'ok': true}
);

_do_sit(cmd) -> (
    fid = cmd:'furniture_id';
    run(str('justSit use ', fid));
    {'ok': true}
);

_do_place_furniture(cmd) -> (
    x = cmd:'x'; y = cmd:'y'; z = cmd:'z';
    ft = cmd:'furniture_type';
    run(str('script run place_furniture("', ft, '",', x, ',', y, ',', z, ')'));
    {'ok': true}
);

_do_trinket(cmd) -> (
    action = cmd:'trinket_action';
    ttype  = cmd:'trinket_type';
    run(str('trinket ', action, ' ', ttype));
    {'ok': true}
);

_do_jei_search(cmd) -> (
    item = cmd:'item_name';
    // JEI has no server-side API — return items matching from registry
    matches = [];
    for(all_items(), i,
        if(matches(str(i), str('.*', item, '.*')),
            matches += [str(i)];
        );
    );
    {'ok': true, 'data': matches}
);

_do_spawn_player(cmd) -> (
    name = cmd:'name';
    x    = cmd:'x'; y = cmd:'y'; z = cmd:'z';
    run(str('player ', name, ' spawn at ', x, ' ', y, ' ', z));
    {'ok': true}
);

_do_set_skin(cmd) -> (
    name = cmd:'name';
    url  = cmd:'skin_url';
    _apply_skin(name, url);
    {'ok': true}
);

_do_run_script(cmd) -> (
    sname  = cmd:'script_name';
    pname  = cmd:'player_name';
    run(str('script run execute_bot_script("', sname, '","', pname, '")'));
    {'ok': true}
);

_do_player_action(cmd) -> (
    pname  = cmd:'player_name';
    action = cmd:'action';
    if(action == 'mine',
        run(str('player ', pname, ' attack once'));
    ,
    if(action == 'place',
        blk = cmd:'block';
        run(str('player ', pname, ' use ', blk));
    ,
    if(action == 'interact',
        run(str('player ', pname, ' use'));
    ,
    if(action == 'move',
        d = cmd:'direction';
        run(str('player ', pname, ' move ', d));
    ))));
    {'ok': true}
);

_do_raw_command(cmd) -> (
    c    = cmd:'command';
    resp = run(c);
    {'ok': true, 'data': str(resp)}
);