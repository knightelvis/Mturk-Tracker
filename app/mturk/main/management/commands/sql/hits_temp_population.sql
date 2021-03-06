declare
  lag_id integer; cur_id integer;
  prj_started integer; prj_completed integer;

begin

  RAISE NOTICE 'Processing crawls from % to % ', istart, iend;

  -- cur_id - the one we are updating
  -- lag_id - previous correct crawl
  FOR cur_id, lag_id IN (
    SELECT (lag(id, 1, NULL) OVER (ORDER BY start_time DESC)), id
     FROM main_crawl
      WHERE
        start_time BETWEEN istart AND iend AND
        groups_available * 0.9 < groups_downloaded
      ORDER BY start_time DESC)
  LOOP
    IF(lag_id IS NOT NULL AND cur_id IS NOT NULL AND lag_id <> cur_id) THEN
      RAISE NOTICE 'lag_id % cur_id % ', lag_id, cur_id;

      /* Inserts (hits_diff, group_id, group_id, crawl_id, prev_crawl_id) into
       * hits_temp.
       *
       * Note that we are saving both a.group_id and b.group_id. This can be
       * used to find moments where a project has disappeared.
       * HOWEVER repeating the join is a faster query than selecting from newly
       * created hits_temp.
      */
      DELETE FROM hits_temp WHERE crawl_id=cur_id;
      INSERT INTO hits_temp(
        SELECT (coalesce(a.hits_available, 0) - coalesce(b.hits_available, 0)),
          a.group_id, b.group_id, cur_id, lag_id FROM (
            (SELECT group_id, hits_available FROM main_hitgroupstatus
              WHERE crawl_id = cur_id) a
            FULL OUTER JOIN
            (SELECT group_id, hits_available FROM main_hitgroupstatus
              WHERE crawl_id = lag_id) b
            ON a.group_id = b.group_id));

      /* Finds the count of hitgroups started between the crawls. */
      SELECT count(1) INTO prj_started FROM (
        (SELECT group_id FROM main_hitgroupstatus WHERE crawl_id=cur_id) a
        FULL OUTER JOIN
        (SELECT group_id FROM main_hitgroupstatus WHERE crawl_id=lag_id) b
        ON a.group_id=b.group_id) WHERE b.group_id IS NULL;

      /* Finds the count of hitgroups completed between the crawls. */
      SELECT count(1) INTO prj_completed FROM (
        (SELECT group_id FROM main_hitgroupstatus WHERE crawl_id=cur_id) a
        FULL OUTER JOIN
        (SELECT group_id FROM main_hitgroupstatus WHERE crawl_id=lag_id) b
        ON a.group_id=b.group_id) WHERE a.group_id IS NULL;

      /* Updates crawlagregates. */
      UPDATE main_crawlagregates
        SET hitgroups_posted = prj_started, hitgroups_consumed = prj_completed
        WHERE crawl_id=cur_id;
    END IF;

    if(cur_id % 100 = 0) then
      RAISE NOTICE 'Processing id % ', cur_id;
    end if;

  END LOOP;
END;
