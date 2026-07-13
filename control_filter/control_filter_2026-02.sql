INSTALL aixchess FROM community;
LOAD aixchess;

COPY (
    WITH exploded_games AS (
        SELECT 
            lichess_id,
            result,
            UNNEST(range(2, length(evals) + 1)) AS ply,
            evals,
            clocks_white,
            clocks_black,
            move_details(movedata) AS moves
        FROM 'aix_lichess_2026-02_low.parquet'
        WHERE 
            time_increment = 0 
            AND time_initial IN (60, 180)
            AND length(evals) >= 2
    ),
    sound_checks AS (
        SELECT 
            lichess_id,
            ply,
            result,
            CASE WHEN ply % 2 = 1 THEN 'White' ELSE 'Black' END AS crisc_player
        FROM exploded_games
        WHERE 
            moves[ply].is_check = TRUE
            AND (
                CASE 
                    WHEN ply % 2 = 1 THEN clocks_black[CAST(floor(ply / 2.0) AS INTEGER)] 
                    ELSE clocks_white[CAST(floor(ply / 2.0) AS INTEGER)]
                END
            ) <= 5
            AND (
                CASE 
                    WHEN ply % 2 = 1 THEN eval_to_centipawns(evals[ply]) - eval_to_centipawns(evals[ply - 1])
                    ELSE (eval_to_centipawns(evals[ply]) - eval_to_centipawns(evals[ply - 1])) * -1
                END
            ) >= -50
    )
    SELECT * FROM sound_checks ORDER BY random() LIMIT 21500
) TO 'control_checks_2026-02.csv' (HEADER, DELIMITER ',');
