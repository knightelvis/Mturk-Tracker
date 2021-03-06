declare
i integer;
/* Hits temp is: (hits_diff, group_id, group_id, crawl_id, crawl_id - 1) */
CUR1 CURSOR FOR SELECT * FROM hits_temp
  WHERE crawl_id IN (
    SELECT id FROM main_crawl WHERE start_time BETWEEN istart AND iend);

begin
  RAISE NOTICE 'Processing crawls from % to %.', istart, iend;
  i :=1;
  FOR REC IN CUR1
  LOOP
    /* Sets both hits_posted and hits_consumed to 0. */
    update hits_mv
      set hits_posted = 0 , hits_consumed = 0
      where group_id = REC.group_id1 and crawl_id = REC.crawl_id;

    /* Sets hits_posted or hits_consumed. */
    if(REC.hits >= 0) then
      update hits_mv
        set hits_posted = REC.hits
        where group_id = REC.group_id1 and crawl_id = REC.crawl_id;
    else
      update hits_mv
        set hits_consumed = (-1) * REC.hits
        where group_id = REC.group_id2 and crawl_id = REC.prev_crawl_id;
    end if;
    if(i % 1000 = 0) then
      RAISE NOTICE 'Processing crawl % ', i;
    end if;
    i := i+1;
  END LOOP;

  RAISE NOTICE 'Delecting hits_temp records from % to %.', istart, iend;

  TRUNCATE hits_temp;

  -- DELETE FROM hits_temp
  --   WHERE crawl_id IN (
  --     SELECT id FROM main_crawl
  --     WHERE start_time BETWEEN istart AND iend
  --   );

  RAISE NOTICE 'Finishing.';
END;
