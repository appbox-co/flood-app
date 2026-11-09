-- Register 4.16.1-0.16.25-1 as a private release candidate by copying the
-- 4.16.1-0.16.25 resource contract and its version-specific password field.
-- -1 creates the default Flood user when users.db exists but holds no users,
-- which installs that ran Flood without authentication can have; 0.16.25
-- served the first-run registration page to them. 0.16.25 stays the default.
-- Run only after the exact image passes the release gate and registry verification.
BEGIN;
DO $release$
DECLARE
    baseline app_versions%ROWTYPE;
    candidate app_versions%ROWTYPE;
    new_id integer;
    affected integer;
BEGIN
    PERFORM 1 FROM apps WHERE id=82 AND version='4.16.1-0.16.25'
        AND tag='4.16.1-0.16.25' AND app_slots=1 AND "Memory"=0
        AND "MemorySwap"=0 AND "MemoryReservation"=0 AND "CPUs"=0
        AND allow_downgrade=1 AND registry='repo.cylo.io' AND "Image"='flood' FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'App baseline changed'; END IF;
    SELECT * INTO STRICT baseline FROM app_versions
        WHERE id=1509 AND app_id=82 AND version='4.16.1-0.16.25'
        AND is_default=1 AND enabled=1 AND admin_only=0
        AND tag='4.16.1-0.16.25'
        AND installed_image_digest='repo.cylo.net/flood@sha256:31c37755be7738668134bdffc1a70fe4af55433024304f0a3e7222ce4d7a2ca8' FOR UPDATE;
    IF baseline.memory<>0 OR baseline.memory_swap<>0
        OR baseline.memory_reservation<>0 OR baseline.cpus<>0
        OR baseline.app_slots<>1 OR baseline.tcp_dynamic_ports<>1
        OR baseline.udp_dynamic_ports<>1 OR baseline.pids_limit<>0
        OR baseline.combined_dynamic_ports IS NOT NULL OR baseline.init<>1
    THEN RAISE EXCEPTION 'Version resource baseline changed'; END IF;
    IF EXISTS (SELECT 1 FROM app_versions WHERE app_id=82
        AND version='4.16.1-0.16.25-1')
    THEN RAISE EXCEPTION 'Release already registered'; END IF;

    INSERT INTO app_versions (
        app_id,version,tag,enabled,is_default,changes,min_memory,min_cpus,
        deprecated,deprecation_message,created_at,updated_at,user_id,admin_only,
        memory,memory_swap,memory_reservation,cpus,init,privileged,cap_add,cap_drop,
        tcp_port_range,udp_port_range,tcp_dynamic_ports,udp_dynamic_ports,pids_limit,
        combined_port_range,combined_dynamic_ports,app_slots,image,
        custom_field_preinstall_description,custom_field_postinstall_description,installed_image_digest
    ) SELECT app_id,'4.16.1-0.16.25-1','4.16.1-0.16.25-1',1,0,
        'Fixes Flood asking you to create an account instead of showing its login page. This could happen after updating an older Flood install to 4.16.1-0.16.25. Flood now sets up your login with your app username and password, the same ones you use in the browser sign-in box, and changing the password from the dashboard works again. If you already have a Flood login, it stays as it is. Your torrents, downloads and settings are not changed by the update.',
        min_memory,min_cpus,0,NULL,now(),now(),2,1,
        memory,memory_swap,memory_reservation,cpus,init,privileged,cap_add,cap_drop,
        tcp_port_range,udp_port_range,tcp_dynamic_ports,udp_dynamic_ports,pids_limit,
        combined_port_range,combined_dynamic_ports,app_slots,image,
        custom_field_preinstall_description,custom_field_postinstall_description,'repo.cylo.net/flood@sha256:8354a11d343e187c5965e0d0ec9269ee452f57484cd6aed0eb996a4c89261acb'
        FROM app_versions WHERE id=baseline.id RETURNING id INTO new_id;
    GET DIAGNOSTICS affected=ROW_COUNT;
    IF affected<>1 THEN RAISE EXCEPTION 'Expected one new version'; END IF;
    SELECT * INTO STRICT candidate FROM app_versions WHERE id=new_id;
    IF (to_jsonb(candidate)-ARRAY['id','version','tag','enabled','is_default','changes','deprecated','deprecation_message','created_at','updated_at','user_id','admin_only','installed_image_digest'])
        IS DISTINCT FROM
       (to_jsonb(baseline)-ARRAY['id','version','tag','enabled','is_default','changes','deprecated','deprecation_message','created_at','updated_at','user_id','admin_only','installed_image_digest'])
    THEN RAISE EXCEPTION 'Resource parity failed'; END IF;

    INSERT INTO customfields (
        type,relid,relid2,fname,display_name,fieldtype,description,default_value,
        required,options,regex,adminonly,sort_order,flex,customtable_editable,
        template_type,"minLength","maxLength",version,app_version_id,stable_id,
        condition_json,sensitive,revealable,"unique"
    ) SELECT type,relid,relid2,fname,display_name,fieldtype,description,default_value,
        required,options,regex,adminonly,sort_order,flex,customtable_editable,
        template_type,"minLength","maxLength",'4.16.1-0.16.25-1',new_id,stable_id,
        condition_json,sensitive,revealable,"unique"
        FROM customfields WHERE type='app' AND relid=82
            AND version=baseline.version AND app_version_id=baseline.id
            AND fname='PASSWORD' AND fieldtype='complexPassword'
            AND template_type='password' AND sensitive AND revealable
            AND options::jsonb='{"showOnInstalled": true}'::jsonb;
    GET DIAGNOSTICS affected=ROW_COUNT;
    IF affected<>1 THEN RAISE EXCEPTION 'Expected one version-specific field'; END IF;
END;
$release$;
COMMIT;
