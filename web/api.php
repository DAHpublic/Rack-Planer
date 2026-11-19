<?php
/*
 * Rack-Planer – Webversion: Speicher auf dem Server (PHP, ohne Datenbank).
 *
 * Gerechnet und gezeichnet wird im Browser (app/*.js). Dieses Skript speichert nur:
 *   daten/schraenke/<id>.rack.json   je Schrank eine Projektdatei – dasselbe Format wie die
 *                                    Desktop-Version (inkl. Historie)
 *   daten/eigene-vorlagen.json       im Browser angelegte Vorlagen
 * Die mitgelieferten Vorlagen stehen in vorlagen.json (wird bei jedem Update ersetzt).
 *
 * Aufruf: api.php?p=<pfad>[&m=PUT|DELETE]   (PUT/DELETE kommen als POST mit m=…)
 *   GET  info                 Version, Update möglich?
 *   GET  templates            alle Vorlagen      POST templates   eigene Vorlage anlegen
 *   POST templates/<id>&m=DELETE                 eigene Vorlage löschen
 *   GET  racks                Liste              POST racks       neuer Schrank / Import
 *   GET  racks/<id>           laden              POST racks/<id>&m=PUT   speichern (Historie)
 *   POST racks/<id>&m=DELETE  löschen
 *   POST update               Update-ZIP einspielen (Feld „datei“; nur mit web_update = true)
 *   POST update/jetzt         neueste Version sofort von GitHub holen (nur mit web_update = true)
 *   GET  autoupdate           automatisches Update: prüft nur im Zeitfenster (nachts) und höchstens
 *                             einmal je Nacht – für den Aufgabenplaner (curl/wget) gedacht
 *
 * Kommandozeile: php api.php autoupdate [--jetzt]   (--jetzt: ohne Zeitfenster, sofort prüfen)
 *
 * Einstellungen: einstellungen.ini (wird von Updates nie überschrieben, fehlt sie, wird sie
 * mit den Standardwerten angelegt).
 *
 * Läuft mit PHP 7.4 bis 8.x ohne zusätzliche Erweiterungen. Updates brauchen „zip“, das
 * automatische Update außerdem „curl“ (oder allow_url_fopen mit „openssl“).
 */

declare(strict_types=1);

date_default_timezone_set(ini_get('date.timezone') ?: 'Europe/Berlin');

const APP_DIR = __DIR__;
$dataDir = getenv('RACK_DATA') ?: (APP_DIR . DIRECTORY_SEPARATOR . 'daten');
define('DATA_DIR', rtrim($dataDir, '/\\'));
define('RACK_DIR', DATA_DIR . DIRECTORY_SEPARATOR . 'schraenke');
define('OWN_TPL_FILE', DATA_DIR . DIRECTORY_SEPARATOR . 'eigene-vorlagen.json');
define('SETTINGS_FILE', APP_DIR . DIRECTORY_SEPARATOR . 'einstellungen.ini');
define('SETTINGS_TEMPLATE', APP_DIR . DIRECTORY_SEPARATOR . 'app' . DIRECTORY_SEPARATOR . 'einstellungen-standard.txt');
define('UPDATE_STATE', APP_DIR . DIRECTORY_SEPARATOR . '.autoupdate.json');
define('UPDATE_LOCK', APP_DIR . DIRECTORY_SEPARATOR . '.update.lock');
define('UPDATE_DOWNLOAD', APP_DIR . DIRECTORY_SEPARATOR . '.update-download.zip');
const SETTINGS_DEFAULTS = [
    'auto_update' => true, 'auto_update_von' => '00:30', 'auto_update_bis' => '03:30',
    'web_update' => false, 'quelle' => 'DAHpublic/Rack-Planer', 'server_speichern' => true,
];
// Dateien im Programmordner, die ein Update nie ersetzt oder löscht
const UPDATE_KEEP = ['einstellungen.ini', '.autoupdate.json', '.update.lock', '.update-download.zip'];
const UPDATE_MAX_BYTES = 60 * 1024 * 1024;
const OWN_GROUP = 'Eigene Vorlagen';
const SHELF_WIDTH_MM = 450;
const CATEGORIES = ['NAS', 'Firewall', 'Server', 'USV', 'Switch', 'Router', 'NVR', 'Telefonanlage',
    'Patchpanel', 'Zubehör', 'Sonstiges'];
const JSON_FLAGS = JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRESERVE_ZERO_FRACTION;

// Dateien, die ein Update ersetzen darf (alles andere im ZIP wird ignoriert)
const UPDATE_EXT = ['php', 'html', 'js', 'css', 'json', 'svg', 'ttf', 'txt', 'md', 'png', 'ico', 'bat', 'htaccess', 'ini'];

/* ------------------------------------------------------------------------------------ */
/* Hilfen                                                                                 */
/* ------------------------------------------------------------------------------------ */

final class HttpError extends Exception
{
    public $status;
    public $extra;

    public function __construct(int $status, string $message, array $extra = [])
    {
        parent::__construct($message);
        $this->status = $status;
        $this->extra = $extra;
    }
}

function send($data, int $status = 200): void
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRESERVE_ZERO_FRACTION);
}

/** Text auf höchstens $n Zeichen kürzen (UTF-8, ohne die Erweiterung mbstring). */
function str_cut(string $s, int $n): string
{
    return preg_match('/^.{0,' . $n . '}/us', $s, $m) ? $m[0] : substr($s, 0, $n);
}

function now_iso(): string
{
    return date('Y-m-d\TH:i:s');
}

function body(): array
{
    $raw = file_get_contents('php://input');
    if ($raw === '' || $raw === false) {
        return [];
    }
    $data = json_decode($raw, true);
    if (!is_array($data)) {
        throw new HttpError(400, 'Ungültige Anfrage (kein JSON).');
    }
    return $data;
}

function ensure_dir(string $dir): void
{
    if (!is_dir($dir) && !@mkdir($dir, 0775, true) && !is_dir($dir)) {
        throw new HttpError(500, "Der Ordner „" . basename($dir) . "“ kann nicht angelegt werden. "
            . 'Bitte dem Webserver Schreibrechte auf den Rack-Planer-Ordner geben (siehe Anleitung).');
    }
}

function protect_data_dir(): void
{
    ensure_dir(DATA_DIR);
    // Apache: kein direkter Abruf der Daten über den Browser
    $ht = DATA_DIR . DIRECTORY_SEPARATOR . '.htaccess';
    if (!is_file($ht)) {
        @file_put_contents($ht, "Require all denied\nDeny from all\n");
    }
    $idx = DATA_DIR . DIRECTORY_SEPARATOR . 'index.html';
    if (!is_file($idx)) {
        @file_put_contents($idx, '');
    }
}

/** Atomar schreiben: Hilfsdatei im selben Ordner, dann umbenennen. */
function write_atomic(string $path, string $content): void
{
    ensure_dir(dirname($path));
    $tmp = $path . '.' . bin2hex(random_bytes(4)) . '.tmp';
    if (@file_put_contents($tmp, $content, LOCK_EX) === false) {
        throw new HttpError(500, "„" . basename($path) . "“ kann nicht gespeichert werden – fehlen Schreibrechte?");
    }
    if (!@rename($tmp, $path)) {
        // Windows: rename über eine vorhandene Datei kann scheitern
        @unlink($path);
        if (!@rename($tmp, $path)) {
            @unlink($tmp);
            throw new HttpError(500, "„" . basename($path) . "“ kann nicht gespeichert werden.");
        }
    }
}

function read_json(string $path, $default = null)
{
    if (!is_file($path)) {
        return $default;
    }
    $data = json_decode((string)file_get_contents($path), true);
    return is_array($data) ? $data : $default;
}

/** Alle schreibenden Zugriffe nacheinander (eine Sperrdatei für den ganzen Speicher). */
function with_lock(callable $fn)
{
    require_server_save();
    protect_data_dir();
    $fh = fopen(DATA_DIR . DIRECTORY_SEPARATOR . '.lock', 'c');
    if ($fh === false) {
        throw new HttpError(500, 'Der Datenordner ist nicht beschreibbar.');
    }
    flock($fh, LOCK_EX);
    try {
        return $fn();
    } finally {
        flock($fh, LOCK_UN);
        fclose($fh);
    }
}

/** Wahrheitswert aus der INI-Datei (true/false, on/off, yes/no, an/aus, ja/nein, 1/0). */
function to_bool($v, bool $default): bool
{
    if (is_bool($v)) {
        return $v;
    }
    if (is_int($v) || is_float($v)) {
        return $v != 0;
    }
    $t = strtolower(trim((string)$v));
    if (in_array($t, ['1', 'true', 'on', 'yes', 'an', 'ein', 'ja'], true)) {
        return true;
    }
    if (in_array($t, ['0', 'false', 'off', 'no', 'aus', 'nein', 'none', ''], true)) {
        return false;
    }
    return $default;
}

/** Fehlt einstellungen.ini, aus der mitgelieferten Vorlage anlegen (ohne Fehler, falls das nicht geht). */
function ensure_settings_file(): void
{
    if (!is_file(SETTINGS_FILE) && is_file(SETTINGS_TEMPLATE)) {
        @copy(SETTINGS_TEMPLATE, SETTINGS_FILE);
    }
}

$SETTINGS_ERROR = '';

/** Einstellungen: Standardwerte, überschrieben von einstellungen.ini (Abschnitte sind egal). */
function settings(): array
{
    static $s = null;
    global $SETTINGS_ERROR;
    if ($s !== null) {
        return $s;
    }
    $s = SETTINGS_DEFAULTS;
    ensure_settings_file();
    if (!is_file(SETTINGS_FILE)) {
        return $s;
    }
    $ini = @parse_ini_file(SETTINGS_FILE, true, INI_SCANNER_TYPED);
    if (!is_array($ini)) {
        $SETTINGS_ERROR = 'einstellungen.ini ist fehlerhaft und wird ignoriert (es gelten die Standardwerte).';
        return $s;
    }
    $flat = [];
    foreach ($ini as $k => $v) {
        if (is_array($v)) {
            foreach ($v as $k2 => $v2) {
                $flat[strtolower((string)$k2)] = $v2;
            }
        } else {
            $flat[strtolower((string)$k)] = $v;
        }
    }
    foreach (SETTINGS_DEFAULTS as $k => $def) {
        if (!array_key_exists($k, $flat)) {
            continue;
        }
        $s[$k] = is_bool($def) ? to_bool($flat[$k], $def) : trim((string)$flat[$k]);
    }
    foreach (['auto_update_von', 'auto_update_bis'] as $k) {
        if (!preg_match('/^([01]?\d|2[0-3]):[0-5]\d$/', $s[$k])) {
            $s[$k] = SETTINGS_DEFAULTS[$k];
        }
    }
    if (!preg_match('#^[\w.-]+/[\w.-]+$#', $s['quelle'])) {
        $s['quelle'] = SETTINGS_DEFAULTS['quelle'];
    }
    return $s;
}

function server_save_allowed(): bool
{
    return settings()['server_speichern'];
}

/** Schreibzugriffe auf „daten“ nur, wenn das Speichern auf dem Server erlaubt ist. */
function require_server_save(): void
{
    if (!server_save_allowed()) {
        throw new HttpError(403, 'Das Speichern auf dem Server ist abgeschaltet (einstellungen.ini: server_speichern = false). '
            . 'Schränke bitte als Datei herunterladen.');
    }
}

function app_version(): string
{
    $v = read_json(APP_DIR . DIRECTORY_SEPARATOR . 'version.json');
    if ($v && isset($v['version'])) {
        return (string)$v['version'];
    }
    // Entwicklung im Repository: Version aus rackcore/version.py
    $py = dirname(APP_DIR) . DIRECTORY_SEPARATOR . 'rackcore' . DIRECTORY_SEPARATOR . 'version.py';
    if (is_file($py) && preg_match('/^APP_VERSION = "([^"]+)"/m', (string)file_get_contents($py), $m)) {
        return $m[1];
    }
    return '?';
}

/* ------------------------------------------------------------------------------------ */
/* Vorlagen                                                                               */
/* ------------------------------------------------------------------------------------ */

function builtin_templates_file(): ?string
{
    foreach ([APP_DIR . '/vorlagen.json', dirname(APP_DIR) . '/rackcore/vorlagen.json'] as $f) {
        if (is_file($f)) {
            return $f;
        }
    }
    return null;
}

function units_for_cm(float $cm): int
{
    return max(1, (int)ceil($cm * 10 / 44.45 - 1e-6));
}

function norm_template(array $t): array
{
    $rack = !array_key_exists('rackmount', $t) || (bool)$t['rackmount'];
    $cm = $rack ? 0.0 : (float)($t['height_cm'] ?? 0);
    $hu = $rack ? max(1, (int)($t['height_u'] ?? 1)) : (!empty($t['height_u']) ? (int)$t['height_u'] : units_for_cm($cm));
    return [
        'group' => (string)($t['group'] ?? ''), 'model' => (string)($t['model'] ?? ''),
        'category' => (string)($t['category'] ?? 'Sonstiges'), 'height_u' => $hu, 'rackmount' => $rack,
        'width_mm' => (int)($t['width_mm'] ?? SHELF_WIDTH_MM) ?: SHELF_WIDTH_MM,
        'power_w' => (float)($t['power_w'] ?? 0), 'note' => (string)($t['note'] ?? ''), 'height_cm' => $cm,
        'depth_mm' => (int)($t['depth_mm'] ?? 0), 'rails' => (bool)($t['rails'] ?? false),
        'full_depth' => (bool)($t['full_depth'] ?? false),
    ];
}

function own_templates(): array
{
    $data = read_json(OWN_TPL_FILE, ['vorlagen' => []]);
    return isset($data['vorlagen']) && is_array($data['vorlagen']) ? $data['vorlagen'] : [];
}

function all_templates(): array
{
    $out = [];
    $file = builtin_templates_file();
    $data = $file ? read_json($file, []) : [];
    foreach (($data['vorlagen'] ?? []) as $i => $t) {
        $out[] = ['id' => 's' . $i, 'builtin' => true] + norm_template($t);
    }
    foreach (own_templates() as $t) {
        $out[] = ['id' => (string)($t['id'] ?? ''), 'builtin' => false] + norm_template($t);
    }
    return $out;
}

function add_template(array $t): array
{
    $model = trim((string)($t['model'] ?? ''));
    if ($model === '') {
        throw new HttpError(400, 'Bitte einen Namen für die Vorlage angeben.');
    }
    if (!in_array($t['category'] ?? null, CATEGORIES, true)) {
        throw new HttpError(400, 'Unbekannte Kategorie.');
    }
    $rack = !array_key_exists('rackmount', $t) || (bool)$t['rackmount'];
    $entry = [
        'id' => 'e' . bin2hex(random_bytes(6)),
        'group' => str_cut((string)($t['group'] ?? OWN_GROUP) ?: OWN_GROUP, 100),
        'model' => str_cut($model, 200), 'category' => $t['category'],
        'height_u' => max(1, min(60, (int)($t['height_u'] ?? 1) ?: 1)), 'rackmount' => $rack,
        'width_mm' => max(20, min(SHELF_WIDTH_MM, (int)($t['width_mm'] ?? SHELF_WIDTH_MM) ?: SHELF_WIDTH_MM)),
        'power_w' => max(0.0, (float)($t['power_w'] ?? 0)), 'note' => str_cut((string)($t['note'] ?? ''), 300),
        'height_cm' => (float)($t['height_cm'] ?? 0), 'depth_mm' => max(0, min(2000, (int)($t['depth_mm'] ?? 0))),
        'rails' => (bool)($t['rails'] ?? false),
    ];
    return with_lock(function () use ($entry) {
        $list = own_templates();
        $list[] = $entry;
        write_atomic(OWN_TPL_FILE, json_encode(['vorlagen' => $list], JSON_FLAGS) . "\n");
        return ['id' => $entry['id'], 'builtin' => false] + norm_template($entry);
    });
}

function delete_template(string $id): void
{
    with_lock(function () use ($id) {
        $list = own_templates();
        $new = array_values(array_filter($list, function ($t) use ($id) {
            return (string)($t['id'] ?? '') !== $id;
        }));
        if (count($new) === count($list)) {
            throw new HttpError(404, 'Nur eigene Vorlagen lassen sich löschen.');
        }
        write_atomic(OWN_TPL_FILE, json_encode(['vorlagen' => $new], JSON_FLAGS) . "\n");
    });
}

/* ------------------------------------------------------------------------------------ */
/* Schränke                                                                               */
/* ------------------------------------------------------------------------------------ */

const RACK_KEYS = ['name', 'height_u', 'depth_mm', 'as_of', 'items'];

function rack_path(string $id): string
{
    if (!preg_match('/^[a-f0-9]{12}$/', $id)) {
        throw new HttpError(404, 'Diesen Schrank gibt es nicht (mehr).');
    }
    return RACK_DIR . DIRECTORY_SEPARATOR . $id . '.rack.json';
}

function rack_of(array $doc): array
{
    $r = [];
    foreach (RACK_KEYS as $k) {
        $r[$k] = $doc[$k] ?? null;
    }
    return $r;
}

/** Datei lesen: [Dokument, Revision]. Revision = Prüfsumme des Dateiinhalts. */
function load_rack_file(string $id): array
{
    $path = rack_path($id);
    if (!is_file($path)) {
        throw new HttpError(404, 'Diesen Schrank gibt es nicht (mehr).');
    }
    $raw = (string)file_get_contents($path);
    $doc = json_decode($raw, true);
    if (!is_array($doc)) {
        throw new HttpError(500, 'Die Datei des Schranks ist beschädigt.');
    }
    return [$doc, substr(sha1($raw), 0, 16)];
}

function record(string $id): array
{
    [$doc, $rev] = load_rack_file($id);
    return ['id' => $id, 'revision' => $rev, 'document' => $doc];
}

function summary(string $id, array $doc, string $rev, int $mtime): array
{
    $hist = $doc['history'] ?? [];
    $entries = isset($hist['entries']) && is_array($hist['entries']) ? $hist['entries'] : (array_is_list_compat($hist) ? $hist : []);
    $devices = 0;
    foreach (($doc['items'] ?? []) as $it) {
        if (($it['category'] ?? '') !== 'Fachboden') {
            $devices++;
        }
    }
    return ['id' => $id, 'name' => (string)($doc['name'] ?? ''), 'revision' => $rev,
        'height_u' => $doc['height_u'] ?? null, 'depth_mm' => $doc['depth_mm'] ?? null,
        'as_of' => (string)($doc['as_of'] ?? ''), 'saved_at' => (string)($doc['saved_at'] ?? ''),
        'created' => (string)($doc['created'] ?? ''), 'devices' => $devices, 'history' => count($entries),
        'updated_at' => date('Y-m-d\TH:i:s', $mtime)];
}

function array_is_list_compat($a): bool
{
    if (!is_array($a)) {
        return false;
    }
    $i = 0;
    foreach ($a as $k => $_) {
        if ($k !== $i++) {
            return false;
        }
    }
    return true;
}

function list_racks(): array
{
    $out = [];
    foreach (glob(RACK_DIR . DIRECTORY_SEPARATOR . '*.rack.json') ?: [] as $path) {
        $id = basename($path, '.rack.json');
        if (!preg_match('/^[a-f0-9]{12}$/', $id)) {
            continue;
        }
        $raw = (string)@file_get_contents($path);
        $doc = json_decode($raw, true);
        if (!is_array($doc)) {
            continue;
        }
        $out[] = summary($id, $doc, substr(sha1($raw), 0, 16), (int)filemtime($path));
    }
    usort($out, function ($a, $b) {
        $c = strcasecmp($a['name'], $b['name']);
        return $c !== 0 ? $c : strcmp($b['updated_at'], $a['updated_at']);
    });
    return $out;
}

function encode_doc(array $doc): string
{
    return json_encode($doc, JSON_FLAGS) . "\n";
}

function create_rack(array $doc): array
{
    if (!isset($doc['items']) || !is_array($doc['items'])) {
        throw new HttpError(400, 'Keine Rack-Planer-Projektdatei.');
    }
    if (empty($doc['saved_at'])) {
        $doc['saved_at'] = now_iso();
    }
    return with_lock(function () use ($doc) {
        ensure_dir(RACK_DIR);
        do {
            $id = bin2hex(random_bytes(6));
        } while (is_file(rack_path($id)));
        write_atomic(rack_path($id), encode_doc($doc));
        return record($id);
    });
}

/**
 * Aktuellen Stand speichern. Ist die Historie aktiv und hat sich der Schrank geändert, wandert
 * der bisher gespeicherte Stand in die Historie (wie beim Speichern der Datei in der
 * Desktop-Version).
 */
function save_rack(string $id, array $b): array
{
    $rack = $b['rack'] ?? null;
    if (!is_array($rack) || !isset($rack['items']) || !is_array($rack['items'])) {
        throw new HttpError(400, 'Kein Schrank übergeben.');
    }
    return with_lock(function () use ($id, $b, $rack) {
        [$doc, $rev] = load_rack_file($id);
        $base = $b['base_revision'] ?? null;
        if (empty($b['force']) && $base !== null && (string)$base !== $rev) {
            throw new HttpError(409, 'Der Schrank wurde inzwischen an einem anderen Gerät gespeichert.',
                ['current' => summary($id, $doc, $rev, (int)filemtime(rack_path($id)))]);
        }
        $old = rack_of($doc);
        $new = rack_of($rack);
        $hist = isset($doc['history']) && is_array($doc['history']) && isset($doc['history']['entries'])
            ? $doc['history'] : ['enabled' => false, 'declined' => false, 'entries' => []];
        $added = false;
        if (!empty($b['history_enabled']) && $old != $new) {
            $entries = $hist['entries'];
            $last = $entries ? $entries[count($entries) - 1]['rack'] ?? null : null;
            if ($last != $old) {
                $entries[] = ['saved_at' => (string)($doc['saved_at'] ?? ''), 'as_of' => (string)($old['as_of'] ?? ''),
                    'note' => '', 'rack' => $old];
                $added = true;
            }
            $hist['entries'] = $entries;
        }
        $hist['enabled'] = !empty($b['history_enabled']);
        $hist['declined'] = !empty($b['history_declined']);
        foreach ($new as $k => $v) {
            $doc[$k] = $v;
        }
        $doc['saved_at'] = now_iso();
        $doc['history'] = $hist;
        write_atomic(rack_path($id), encode_doc($doc));
        return record($id) + ['history_added' => $added];
    });
}

function delete_rack(string $id): void
{
    with_lock(function () use ($id) {
        $path = rack_path($id);
        if (!is_file($path) || !@unlink($path)) {
            throw new HttpError(404, 'Diesen Schrank gibt es nicht (mehr).');
        }
    });
}

/* ------------------------------------------------------------------------------------ */
/* Update: neue Programmversion einspielen (ZIP hochladen oder automatisch von GitHub)    */
/*                                                                                        */
/* Ersetzt nur Programmdateien und vorlagen.json. Nie angefasst werden der Ordner „daten“ */
/* und einstellungen.ini (UPDATE_KEEP).                                                   */
/* ------------------------------------------------------------------------------------ */

function web_update_allowed(): bool
{
    return settings()['web_update'];
}

/** Läuft die Webversion als installierter Ordner (aus dem ZIP) – nicht direkt aus dem Repository? */
function is_installed(): bool
{
    return is_file(APP_DIR . DIRECTORY_SEPARATOR . 'version.json');
}

/** Nur ein Update gleichzeitig (eigene Sperrdatei im Programmordner – „daten“ bleibt unberührt). */
function with_update_lock(callable $fn, bool $wait = true)
{
    $fh = @fopen(UPDATE_LOCK, 'c');
    if ($fh === false) {
        throw new HttpError(500, 'Der Webserver darf den Programmordner nicht ändern (Schreibrechte fehlen).');
    }
    if (!flock($fh, $wait ? LOCK_EX : LOCK_EX | LOCK_NB)) {
        fclose($fh);
        throw new HttpError(409, 'Es läuft gerade schon ein Update.');
    }
    try {
        return $fn();
    } finally {
        flock($fh, LOCK_UN);
        fclose($fh);
    }
}

/** Update-ZIP prüfen und einspielen. $expect: erwartete Versionsnummer (beim Download von GitHub). */
function install_zip(string $zipPath, string $expect = ''): array
{
    if (!class_exists('ZipArchive')) {
        throw new HttpError(500, 'Auf dem Server fehlt die PHP-Erweiterung „zip“. Bitte in der Web Station aktivieren '
            . 'oder das Update von Hand einspielen (Ordnerinhalt ersetzen, „daten“ und einstellungen.ini behalten).');
    }
    if (!is_installed()) {
        throw new HttpError(400, 'Update nur für die installierte Webversion (Ordner aus dem ZIP), nicht im Repository.');
    }
    $zip = new ZipArchive();
    if ($zip->open($zipPath) !== true) {
        throw new HttpError(400, 'Die Datei ist kein gültiges ZIP-Archiv.');
    }
    // Wurzel des Programms im ZIP finden (Ordner mit version.json und api.php)
    $prefix = null;
    for ($i = 0; $i < $zip->numFiles; $i++) {
        $n = str_replace('\\', '/', (string)$zip->getNameIndex($i));
        if (preg_match('#^((?:[^/]+/)?)version\.json$#', $n, $m) && $zip->locateName($m[1] . 'api.php') !== false) {
            $prefix = $m[1];
            break;
        }
    }
    if ($prefix === null) {
        $zip->close();
        throw new HttpError(400, 'Das ZIP enthält keine Webversion des Rack-Planers (version.json und api.php fehlen).');
    }
    $ver = json_decode((string)$zip->getFromName($prefix . 'version.json'), true);
    if (!is_array($ver) || ($ver['app'] ?? '') !== 'Rack-Planer' || ($ver['edition'] ?? '') !== 'web') {
        $zip->close();
        throw new HttpError(400, 'Das ZIP ist keine Webversion des Rack-Planers.');
    }
    if ($expect !== '' && (string)($ver['version'] ?? '') !== $expect) {
        $zip->close();
        throw new HttpError(400, "Das ZIP enthält Version „" . ($ver['version'] ?? '?') . "“ statt „{$expect}“.");
    }
    // Dateien prüfen und lesen
    $files = [];
    for ($i = 0; $i < $zip->numFiles; $i++) {
        $n = str_replace('\\', '/', (string)$zip->getNameIndex($i));
        if (strpos($n, $prefix) !== 0 || substr($n, -1) === '/') {
            continue;
        }
        $rel = substr($n, strlen($prefix));
        if ($rel === '' || strpos($rel, '..') !== false || $rel[0] === '/' || preg_match('#^(daten|php)/#i', $rel)) {
            continue;
        }
        // eigene Einstellungen nie überschreiben – nur anlegen, falls sie fehlen
        if (in_array($rel, UPDATE_KEEP, true) && ($rel !== 'einstellungen.ini' || is_file(SETTINGS_FILE))) {
            continue;
        }
        $ext = strtolower(pathinfo($rel, PATHINFO_EXTENSION));
        if (basename($rel) === '.htaccess') {
            $ext = 'htaccess';
        }
        if (!in_array($ext, UPDATE_EXT, true)) {
            continue;
        }
        $content = $zip->getFromIndex($i);
        if ($content === false) {
            $zip->close();
            throw new HttpError(400, "„{$rel}“ im ZIP ist nicht lesbar.");
        }
        $files[$rel] = $content;
    }
    $zip->close();
    if (!isset($files['index.html'], $files['api.php'])) {
        throw new HttpError(400, 'Das ZIP ist unvollständig.');
    }
    $old = read_json(APP_DIR . '/manifest.json', ['files' => []]);
    $oldVersion = app_version();
    // api.php zuletzt schreiben
    uksort($files, function ($a, $b) {
        return ($a === 'api.php') <=> ($b === 'api.php') ?: strcmp($a, $b);
    });
    foreach ($files as $rel => $content) {
        write_atomic(APP_DIR . '/' . $rel, $content);
    }
    // Dateien, die es in der neuen Version nicht mehr gibt, entfernen
    $removed = 0;
    foreach (($old['files'] ?? []) as $rel) {
        $rel = (string)$rel;
        if (!isset($files[$rel]) && !in_array($rel, UPDATE_KEEP, true) && strpos($rel, '..') === false
            && !preg_match('#^(daten|php)/#i', $rel) && is_file(APP_DIR . '/' . $rel)) {
            $removed += @unlink(APP_DIR . '/' . $rel) ? 1 : 0;
        }
    }
    return ['ok' => true, 'old_version' => $oldVersion, 'new_version' => (string)($ver['version'] ?? '?'),
        'files' => count($files), 'removed' => $removed];
}

/** Update-ZIP aus dem Browser (Hilfe → Programm aktualisieren). */
function apply_update(): array
{
    if (!web_update_allowed()) {
        throw new HttpError(403, 'Updates über den Browser sind abgeschaltet (einstellungen.ini: web_update = false).');
    }
    $f = $_FILES['datei'] ?? null;
    if (!$f || ($f['error'] ?? 1) !== UPLOAD_ERR_OK) {
        $err = $f['error'] ?? -1;
        throw new HttpError(400, $err === UPLOAD_ERR_INI_SIZE || $err === UPLOAD_ERR_FORM_SIZE
            ? 'Die Datei ist zu groß für die PHP-Einstellung upload_max_filesize.' : 'Keine Datei empfangen.');
    }
    return with_update_lock(function () use ($f) {
        $r = install_zip($f['tmp_name']);
        log_update(['ergebnis' => 'aktualisiert', 'art' => 'hochgeladen',
            'text' => "Update von Hand: {$r['old_version']} → {$r['new_version']}"]);
        return $r;
    });
}

/* --- automatisches Update von GitHub ------------------------------------------------- */

/** HTTPS-Abruf mit curl (bevorzugt) oder allow_url_fopen. Mit $toFile wird in die Datei geschrieben. */
function http_get(string $url, ?string $toFile = null): string
{
    $ua = 'Rack-Planer-Web/' . app_version() . ' (+https://github.com/' . settings()['quelle'] . ')';
    $headers = ['Accept: ' . ($toFile ? 'application/octet-stream' : 'application/vnd.github+json')];
    if (function_exists('curl_init')) {
        $ch = curl_init($url);
        $fh = null;
        $opts = [CURLOPT_FOLLOWLOCATION => true, CURLOPT_MAXREDIRS => 5, CURLOPT_USERAGENT => $ua,
            CURLOPT_HTTPHEADER => $headers, CURLOPT_CONNECTTIMEOUT => 20, CURLOPT_TIMEOUT => 180,
            CURLOPT_FAILONERROR => false, CURLOPT_MAXFILESIZE => UPDATE_MAX_BYTES];
        if (defined('CURLOPT_PROTOCOLS')) {
            $opts[CURLOPT_PROTOCOLS] = CURLPROTO_HTTPS;
        }
        if ($toFile) {
            $fh = fopen($toFile, 'wb');
            if ($fh === false) {
                throw new HttpError(500, 'Der Webserver darf den Programmordner nicht ändern (Schreibrechte fehlen).');
            }
            $opts[CURLOPT_FILE] = $fh;
        } else {
            $opts[CURLOPT_RETURNTRANSFER] = true;
        }
        curl_setopt_array($ch, $opts);
        $body = curl_exec($ch);
        $code = (int)curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
        $err = curl_error($ch);
        curl_close($ch);
        if ($fh) {
            fclose($fh);
        }
        if ($body === false) {
            throw new HttpError(502, "GitHub ist nicht erreichbar ({$err}).");
        }
        if ($code !== 200) {
            throw new HttpError(502, "GitHub antwortet mit Fehler {$code}.");
        }
        return $toFile ? '' : (string)$body;
    }
    if (!filter_var(ini_get('allow_url_fopen'), FILTER_VALIDATE_BOOLEAN) || !extension_loaded('openssl')) {
        throw new HttpError(500, 'Für das automatische Update braucht PHP die Erweiterung „curl“ '
            . '(Web Station → PHP-Profil → Erweiterungen) oder allow_url_fopen mit „openssl“.');
    }
    $ctx = stream_context_create(['http' => ['method' => 'GET', 'header' => array_merge($headers, ["User-Agent: {$ua}"]),
        'follow_location' => 1, 'max_redirects' => 5, 'timeout' => 180, 'ignore_errors' => true]]);
    $body = @file_get_contents($url, false, $ctx, 0, UPDATE_MAX_BYTES + 1);
    $status = 0;
    foreach (($http_response_header ?? []) as $line) {
        if (preg_match('#^HTTP/\S+\s+(\d{3})#', $line, $m)) {
            $status = (int)$m[1];   // letzte Statuszeile zählt (nach Weiterleitungen)
        }
    }
    if ($body === false) {
        throw new HttpError(502, 'GitHub ist nicht erreichbar.');
    }
    if ($status !== 200) {
        throw new HttpError(502, "GitHub antwortet mit Fehler {$status}.");
    }
    if (strlen($body) > UPDATE_MAX_BYTES) {
        throw new HttpError(502, 'Die Update-Datei ist zu groß.');
    }
    if ($toFile) {
        if (@file_put_contents($toFile, $body) === false) {
            throw new HttpError(500, 'Der Webserver darf den Programmordner nicht ändern (Schreibrechte fehlen).');
        }
        return '';
    }
    return $body;
}

/** Neuestes Release: [Version, Download-Adresse des Web-ZIP, sha256 oder ''] */
function latest_release(): array
{
    $repo = settings()['quelle'];
    $rel = json_decode(http_get("https://api.github.com/repos/{$repo}/releases/latest"), true);
    if (!is_array($rel) || empty($rel['tag_name'])) {
        throw new HttpError(502, 'Die Antwort von GitHub ist unverständlich.');
    }
    $version = preg_replace('/^v/i', '', (string)$rel['tag_name']);
    foreach (($rel['assets'] ?? []) as $a) {
        $name = (string)($a['name'] ?? '');
        if (preg_match('/^Rack-Planer-Web_v(.+)\.zip$/', $name, $m)) {
            $url = (string)($a['browser_download_url'] ?? '');
            if (strpos($url, 'https://github.com/') !== 0) {
                throw new HttpError(502, 'Unerwartete Download-Adresse im Release.');
            }
            $digest = (string)($a['digest'] ?? '');
            return [$m[1], $url, preg_match('/^sha256:([a-f0-9]{64})$/', $digest, $d) ? $d[1] : '', $version];
        }
    }
    return [$version, '', '', $version];
}

function minutes_of(string $hhmm): int
{
    [$h, $m] = array_map('intval', explode(':', $hhmm));
    return $h * 60 + $m;
}

/**
 * Zeitfenster der Nacht, in der $now liegt: Kennung (Datum des Fensterbeginns) oder null,
 * wenn $now außerhalb liegt. Fenster über Mitternacht (z. B. 23:00–02:00) gehen auch.
 */
function update_window(DateTimeImmutable $now): ?string
{
    $s = settings();
    $von = minutes_of($s['auto_update_von']);
    $bis = minutes_of($s['auto_update_bis']);
    $t = (int)$now->format('G') * 60 + (int)$now->format('i');
    if ($von <= $bis) {
        return $t >= $von && $t < $bis ? $now->format('Y-m-d') : null;
    }
    if ($t >= $von) {
        return $now->format('Y-m-d');
    }
    return $t < $bis ? $now->modify('-1 day')->format('Y-m-d') : null;
}

function update_state(): array
{
    return read_json(UPDATE_STATE, []);
}

/** Ergebnis merken (die letzten 20 Einträge) – für Hilfe → Programm aktualisieren. */
function log_update(array $entry): void
{
    $st = update_state();
    $entry = ['zeit' => now_iso()] + $entry;
    $log = array_slice(array_merge([$entry], $st['protokoll'] ?? []), 0, 20);
    $st['protokoll'] = $log;
    if (isset($entry['fenster'])) {
        $st['fenster'] = $entry['fenster'];
        $st['fenster_ok'] = $entry['ergebnis'] !== 'fehler';
        $st['fenster_zeit'] = time();
    }
    @file_put_contents(UPDATE_STATE, json_encode($st, JSON_FLAGS) . "\n", LOCK_EX);
}

/** Muss in dieser Nacht noch geprüft werden? (Nach einem Fehler höchstens einmal je Stunde neu.) */
function auto_update_due(?DateTimeImmutable $now = null): bool
{
    if (!settings()['auto_update'] || !is_installed()) {
        return false;
    }
    $win = update_window($now ?: new DateTimeImmutable());
    if ($win === null) {
        return false;
    }
    $st = update_state();
    if (($st['fenster'] ?? '') !== $win) {
        return true;
    }
    return empty($st['fenster_ok']) && time() - (int)($st['fenster_zeit'] ?? 0) >= 3600;
}

/**
 * Automatisches Update: neuestes Release prüfen und, falls neuer, einspielen.
 * $force: sofort (ohne Zeitfenster und ohne „schon geprüft“) – Kommandozeile --jetzt bzw. Browser.
 */
function auto_update(bool $force = false, string $art = 'automatisch'): array
{
    if (!is_installed()) {
        return ['status' => 'entwicklung', 'text' => 'Kein Update im Repository (nur in der installierten Webversion).'];
    }
    if (!$force && !settings()['auto_update']) {
        return ['status' => 'aus', 'text' => 'Automatisches Update ist abgeschaltet (einstellungen.ini: auto_update = false).'];
    }
    $now = new DateTimeImmutable();
    $win = update_window($now);
    if (!$force && $win === null) {
        $s = settings();
        return ['status' => 'ausserhalb', 'text' => "Geprüft wird nur zwischen {$s['auto_update_von']} und {$s['auto_update_bis']} Uhr "
            . '(Serverzeit ' . $now->format('H:i') . ').'];
    }
    if (!$force && !auto_update_due($now)) {
        return ['status' => 'erledigt', 'text' => 'In dieser Nacht wurde schon geprüft.'];
    }
    try {
        return with_update_lock(function () use ($force, $win, $art) {
            if (!$force && !auto_update_due()) {
                return ['status' => 'erledigt', 'text' => 'In dieser Nacht wurde schon geprüft.'];
            }
            $base = ['art' => $art] + ($win !== null ? ['fenster' => $win] : []);
            try {
                $current = app_version();
                [$latest, $url, $sha, $tag] = latest_release();
                if ($url === '') {
                    $r = ['status' => 'aktuell', 'text' => "Im neuesten Release (v{$tag}) gibt es keine Webversion – nichts zu tun."];
                } elseif (!version_compare($latest, $current, '>')) {
                    $r = ['status' => 'aktuell', 'text' => "Rack-Planer {$current} ist aktuell."];
                } else {
                    @unlink(UPDATE_DOWNLOAD);
                    try {
                        http_get($url, UPDATE_DOWNLOAD);
                        if ($sha !== '' && !hash_equals($sha, (string)hash_file('sha256', UPDATE_DOWNLOAD))) {
                            throw new HttpError(502, 'Die heruntergeladene Datei ist beschädigt (Prüfsumme stimmt nicht).');
                        }
                        $res = install_zip(UPDATE_DOWNLOAD, $latest);
                    } finally {
                        @unlink(UPDATE_DOWNLOAD);
                    }
                    $r = ['status' => 'aktualisiert', 'text' => "Aktualisiert: {$res['old_version']} → {$res['new_version']}.",
                        'old_version' => $res['old_version'], 'new_version' => $res['new_version']];
                }
                log_update($base + ['ergebnis' => $r['status'], 'text' => $r['text']]);
                return $r;
            } catch (HttpError $e) {
                log_update($base + ['ergebnis' => 'fehler', 'text' => $e->getMessage()]);
                throw $e;
            } catch (Throwable $e) {
                log_update($base + ['ergebnis' => 'fehler', 'text' => $e->getMessage()]);
                throw new HttpError(500, 'Update fehlgeschlagen: ' . $e->getMessage());
            }
        }, $force);
    } catch (HttpError $e) {
        if ($e->status === 409) {
            return ['status' => 'laeuft', 'text' => $e->getMessage()];
        }
        return ['status' => 'fehler', 'text' => $e->getMessage()];
    }
}

/** Kurzinfo für die Oberfläche. */
function update_info(): array
{
    $s = settings();
    $st = update_state();
    return ['auto' => $s['auto_update'], 'von' => $s['auto_update_von'], 'bis' => $s['auto_update_bis'],
        'quelle' => $s['quelle'], 'faellig' => auto_update_due(), 'installiert' => is_installed(),
        'curl' => function_exists('curl_init') || (filter_var(ini_get('allow_url_fopen'), FILTER_VALIDATE_BOOLEAN) && extension_loaded('openssl')),
        'protokoll' => array_slice($st['protokoll'] ?? [], 0, 5)];
}

/* ------------------------------------------------------------------------------------ */
/* Routing                                                                                */
/* ------------------------------------------------------------------------------------ */

function route(string $method, string $p)
{
    if ($p === 'info' || $p === 'health') {
        $writable = is_dir(DATA_DIR) ? is_writable(DATA_DIR) : is_writable(dirname(DATA_DIR));
        global $SETTINGS_ERROR;
        $s = settings();
        return ['ok' => true, 'app' => 'Rack-Planer', 'version' => app_version(), 'php' => PHP_VERSION,
            'zip' => class_exists('ZipArchive'), 'writable' => $writable, 'update_allowed' => web_update_allowed(),
            'app_writable' => is_writable(APP_DIR), 'server_save' => $s['server_speichern'],
            'auto_update' => update_info(), 'settings_error' => $SETTINGS_ERROR];
    }
    if ($p === 'templates') {
        if ($method === 'GET') {
            return all_templates();
        }
        if ($method === 'POST') {
            return add_template(body());
        }
    }
    if (preg_match('#^templates/([\w-]+)$#', $p, $m) && $method === 'DELETE') {
        delete_template($m[1]);
        return ['ok' => true];
    }
    if ($p === 'racks') {
        if ($method === 'GET') {
            return list_racks();
        }
        if ($method === 'POST') {
            $doc = body()['document'] ?? null;
            if (!is_array($doc)) {
                throw new HttpError(400, 'Keine Rack-Planer-Projektdatei.');
            }
            return create_rack($doc);
        }
    }
    if (preg_match('#^racks/([\w-]+)$#', $p, $m)) {
        if ($method === 'GET') {
            return record($m[1]);
        }
        if ($method === 'PUT') {
            return save_rack($m[1], body());
        }
        if ($method === 'DELETE') {
            delete_rack($m[1]);
            return ['ok' => true];
        }
    }
    if ($p === 'update' && $method === 'POST') {
        return apply_update();
    }
    if ($p === 'update/jetzt' && $method === 'POST') {
        if (!web_update_allowed()) {
            throw new HttpError(403, 'Updates über den Browser sind abgeschaltet (einstellungen.ini: web_update = false).');
        }
        $r = auto_update(true, 'Browser');
        if ($r['status'] === 'fehler') {
            throw new HttpError(502, $r['text']);
        }
        return $r;
    }
    if ($p === 'autoupdate') {
        return auto_update();
    }
    throw new HttpError(404, 'Unbekannte Adresse.');
}

// Kommandozeile (z. B. Aufgabenplaner): php api.php autoupdate [--jetzt]
if (PHP_SAPI === 'cli') {
    $args = array_slice($argv ?? [], 1);
    if (($args[0] ?? '') !== 'autoupdate') {
        fwrite(STDERR, "Aufruf: php api.php autoupdate [--jetzt]\n");
        exit(2);
    }
    $r = auto_update(in_array('--jetzt', $args, true), 'Kommandozeile');
    echo json_encode($r, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES), "\n";
    exit($r['status'] === 'fehler' ? 1 : 0);
}

try {
    $method = strtoupper($_SERVER['REQUEST_METHOD'] ?? 'GET');
    if ($method === 'POST' && isset($_GET['m']) && in_array(strtoupper((string)$_GET['m']), ['PUT', 'DELETE'], true)) {
        $method = strtoupper((string)$_GET['m']);
    }
    send(route($method, trim((string)($_GET['p'] ?? ''), '/')));
} catch (HttpError $e) {
    send(['detail' => $e->getMessage()] + $e->extra, $e->status);
} catch (Throwable $e) {
    send(['detail' => 'Serverfehler: ' . $e->getMessage()], 500);
}
