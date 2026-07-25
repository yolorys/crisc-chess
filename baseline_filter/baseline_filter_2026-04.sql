INSTALL aixchess FROM community;
LOAD aixchess;

COPY (
    WITH exploded_games AS (
        SELECT 
            lichess_id,
            result,
            white_rating,
            black_rating,
            UNNEST(range(2, length(evals) + 1)) AS ply,
            evals,
            clocks_white,
            clocks_black
        FROM './data/aix_lichess_2026-04_low.parquet'
        WHERE 
            time_increment = 0
            AND time_initial IN (60, 180)
            AND length(evals) >= 2
    ),
    baseline_positions AS (
        SELECT 
            lichess_id,
            ply,
            result,
            CASE WHEN ply % 2 = 1 THEN 'White' ELSE 'Black' END AS player,
            white_rating,
            black_rating,
            CASE 
                WHEN ply % 2 = 1 THEN clocks_white[CAST(floor(ply / 2.0) AS INTEGER)] 
                ELSE clocks_black[CAST(floor(ply / 2.0) AS INTEGER)]
            END AS player_time,
            CASE 
                WHEN ply % 2 = 1 THEN clocks_black[CAST(floor(ply / 2.0) AS INTEGER)] 
                ELSE clocks_white[CAST(floor(ply / 2.0) AS INTEGER)]
            END AS opponent_time,
            CASE WHEN ply % 2 = 1 THEN white_rating ELSE black_rating END AS player_elo
        FROM exploded_games
        WHERE
            eval_to_centipawns(evals[ply - 1]) BETWEEN -150 AND 150
    ),
    bracketed_positions AS (
        SELECT 
            lichess_id,
            ply,
            result,
            player,
            player_elo,
            CASE 
                WHEN opponent_time <= 5 AND player_time <= 5 THEN '<=5s vs <=5s'
                WHEN opponent_time <= 5 AND player_time > 5 AND player_time <= 10 THEN '<=5s vs 5-10s'
                WHEN opponent_time <= 5 AND player_time > 10 AND player_time <= 15 THEN '<=5s vs 10-15s'
                WHEN opponent_time <= 5 AND player_time > 15 AND player_time <= 20 THEN '<=5s vs 15-20s'
            END AS time_scramble_bracket
        FROM baseline_positions
        WHERE 
            opponent_time <= 5
            AND player_time <= 20
            AND abs(white_rating - black_rating) <= 200
        QUALIFY ROW_NUMBER() OVER (PARTITION BY lichess_id ORDER BY ply ASC) = 1
    )
    SELECT lichess_id, ply, result, player, time_scramble_bracket, player_elo
    FROM bracketed_positions ORDER BY random() LIMIT 21500
) TO './baseline_moves/baseline_moves_2026-04.csv' (HEADER, DELIMITER ',');
