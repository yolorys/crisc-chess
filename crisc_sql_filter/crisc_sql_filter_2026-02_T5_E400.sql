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
            clocks_black,
            move_details(movedata) AS moves
        FROM './data/aix_lichess_2026-02_low.parquet'
        WHERE
            time_increment = 0
            AND time_initial IN (60, 180)
            AND length(evals) >= 2
    ),
    candidate_criscs AS (
        SELECT
            lichess_id,
            ply,
            result,
            CASE WHEN ply % 2 = 1 THEN 'White' ELSE 'Black' END AS player,
            [m."from" || m."to" || m.promotion FOR m IN moves] AS move_list,
            moves,
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
            CASE
                WHEN ply % 2 = 1 THEN eval_to_centipawns(evals[ply]) - eval_to_centipawns(evals[ply - 1])
                ELSE (eval_to_centipawns(evals[ply]) - eval_to_centipawns(evals[ply - 1])) * -1
            END AS eval_drop,
            eval_to_centipawns(evals[ply - 1]) AS pre_move_eval,
            CASE WHEN ply % 2 = 1 THEN white_rating ELSE black_rating END AS player_elo
        FROM exploded_games
    )
    SELECT
        lichess_id,
        ply,
        result,
        player,
        player_elo,
        move_list,
        CASE
            WHEN player_time <= 5  THEN '<=5s vs <=5s'
            WHEN player_time <= 10 THEN '<=5s vs 5-10s'
            WHEN player_time <= 15 THEN '<=5s vs 10-15s'
            WHEN player_time <= 20 THEN '<=5s vs 15-20s'
        END AS time_scramble_bracket
    FROM candidate_criscs
    WHERE
        moves[ply].is_check = TRUE
        AND opponent_time <= 5
        AND player_time <= 20
        AND eval_drop <= -400
        AND pre_move_eval BETWEEN -150 AND 150
        AND abs(white_rating - black_rating) <= 200
    QUALIFY ROW_NUMBER() OVER (PARTITION BY lichess_id ORDER BY ply ASC) = 1
) TO './candidate_criscs/candidate_criscs_2026-02_T5_E400.csv' (HEADER, DELIMITER ',');
