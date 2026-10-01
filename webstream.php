<?php
/**
 * ShionMusicBot — web audio streamer.
 *
 * Server-side Testweb3 client + range-aware audio proxy.
 *   ?action=search&q=…     → JSON search results
 *   ?action=resolve&id=…   → JSON track info (proxied stream URL)
 *   ?action=proxy&u=…      → audio passthrough (Testweb3 hosts only)
 *   default                → player UI
 */

require_once __DIR__ . '/runner_lib.php';

function yt_base(): string
{
    $base = sh_env('YT_API_BASE', 'http://Testweb3.cstsc.in/yt/');
    return rtrim($base, '/') . '/';
}

function yt_host_whitelist(): array
{
    $host = parse_url(yt_base(), PHP_URL_HOST) ?: 'Testweb3.cstsc.in';
    return array($host, strtolower((string) $host));
}

$action = isset($_GET['action']) ? (string) $_GET['action'] : '';

if ($action === 'search' || $action === 'resolve') {
    header('Content-Type: application/json; charset=utf-8');

    if ($action === 'search') {
        $q = isset($_GET['q']) ? trim((string) $_GET['q']) : '';
        if ($q === '' || mb_strlen($q) < 2) {
            echo json_encode(array('ok' => false, 'error' => 'empty query'));
            exit;
        }
        $resp = sh_http_get(yt_base() . 'api.php?' . http_build_query(array('action' => 'search', 'q' => $q)), 25);
        $data = json_decode($resp['body'], true);
        if (!is_array($data) || empty($data['ok'])) {
            echo json_encode(array('ok' => false, 'error' => 'search failed'));
            exit;
        }
        $videos = array();
        foreach ((array) ($data['data']['videos'] ?? array()) as $v) {
            if (!is_array($v) || empty($v['id']) || !empty($v['is_live'])) {
                continue;
            }
            $videos[] = array(
                'id' => (string) $v['id'],
                'title' => (string) ($v['title'] ?? ''),
                'channel' => (string) ($v['channel'] ?? ''),
                'duration_text' => (string) ($v['duration_text'] ?? ''),
                'thumbnail' => (string) ($v['thumbnail'] ?? ''),
            );
            if (count($videos) >= 12) {
                break;
            }
        }
        echo json_encode(array('ok' => true, 'videos' => $videos));
        exit;
    }

    $id = isset($_GET['id']) ? preg_replace('/[^0-9A-Za-z_-]/', '', (string) $_GET['id']) : '';
    if ($id === '') {
        echo json_encode(array('ok' => false, 'error' => 'missing id'));
        exit;
    }
    $resp = sh_http_get(yt_base() . 'api.php?' . http_build_query(array('action' => 'video', 'id' => $id)), 25);
    $data = json_decode($resp['body'], true);
    if (!is_array($data) || empty($data['ok'])) {
        echo json_encode(array('ok' => false, 'error' => 'resolve failed'));
        exit;
    }
    $info = (array) ($data['data'] ?? array());
    $stream = '';
    if (!empty($info['recovery_stream']['url'])) {
        $stream = yt_base() . ltrim((string) $info['recovery_stream']['url'], '/');
    }
    echo json_encode(array(
        'ok' => true,
        'id' => (string) ($info['id'] ?? $id),
        'title' => (string) ($info['title'] ?? ''),
        'channel' => (string) ($info['channel'] ?? ''),
        'duration_text' => (string) ($info['duration_text'] ?? ''),
        'thumbnail' => (string) ($info['thumbnail'] ?? ''),
        'stream' => $stream !== ''
            ? 'webstream.php?action=proxy&u=' . rtrim(strtr(base64_encode($stream), '+/', '-_'), '=')
            : '',
    ));
    exit;
}

if ($action === 'proxy') {
    $raw = isset($_GET['u']) ? (string) $_GET['u'] : '';
    $url = base64_decode(strtr($raw, '-_', '+/'));
    if ($url === false || strpos($url, 'http://') !== 0) {
        http_response_code(400);
        exit("Bad request\n");
    }
    $host = strtolower((string) (parse_url($url, PHP_URL_HOST) ?: ''));
    if (!in_array($host, yt_host_whitelist(), true)) {
        http_response_code(403);
        exit("Host not allowed\n");
    }

    @set_time_limit(0);
    header('Accept-Ranges: bytes');

    $ch = curl_init($url);
    $reqHeaders = array();
    if (isset($_SERVER['HTTP_RANGE'])) {
        $reqHeaders[] = 'Range: ' . $_SERVER['HTTP_RANGE'];
    }
    if ($reqHeaders) {
        curl_setopt($ch, CURLOPT_HTTPHEADER, $reqHeaders);
    }
    $statusSent = false;
    curl_setopt($ch, CURLOPT_HEADERFUNCTION, function ($ch, $line) use (&$statusSent) {
        $trim = trim($line);
        foreach (array('content-type', 'content-length', 'content-range', 'accept-ranges', 'location') as $forward) {
            if (stripos($trim, $forward) === 0) {
                header($trim);
                break;
            }
        }
        return strlen($line);
    });
    curl_setopt($ch, CURLOPT_WRITEFUNCTION, function ($ch, $chunk) {
        echo $chunk;
        if (function_exists('flush')) {
            @flush();
        }
        return strlen($chunk);
    });
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 0);
    curl_exec($ch);
    $code = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    if ($code >= 400 && !$statusSent) {
        http_response_code(502);
    }
    exit;
}

require_once __DIR__ . '/inc/ui.php';
sh_header('webstream', 'Web Player', 'Search and listen right here — streams resolve through the Testweb3 engine.');
?>

<div class="searchbox">
  <input id="q" type="search" placeholder="Search songs… (powered by Testweb3)" autocomplete="off">
  <button class="btn btn-telegram" id="go"><?php echo sh_icon('search', 15); ?> Search</button>
</div>

<div id="results"></div>

<section class="card playercard" id="player" style="display:none">
  <h3 id="ptitle" style="justify-content:center"></h3>
  <img id="pthumb" alt="" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='340' height='190'%3E%3Crect width='100%25' height='100%25' fill='%23141a2e'/%3E%3C/svg%3E">
  <p class="muted" id="pmeta"></p>
  <audio id="audio" controls preload="none"></audio>
</section>

<script>
(function () {
  var q = document.getElementById('q');
  var go = document.getElementById('go');
  var results = document.getElementById('results');
  var player = document.getElementById('player');
  var audio = document.getElementById('audio');

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function search() {
    var query = q.value.trim();
    if (query.length < 2) { return; }
    results.innerHTML = '<p class="muted">Searching…</p>';
    fetch('webstream.php?action=search&q=' + encodeURIComponent(query))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.ok || !data.videos.length) {
          results.innerHTML = '<p class="muted">No results.</p>';
          return;
        }
        results.innerHTML = '';
        data.videos.forEach(function (v) {
          var row = document.createElement('div');
          row.className = 'result';
          row.innerHTML =
            '<img loading="lazy" alt="" src="' + esc(v.thumbnail) + '">' +
            '<div class="meta"><div class="title">' + esc(v.title) + '</div>' +
            '<div class="sub">' + esc(v.channel) + '</div></div>' +
            '<span class="dur">' + esc(v.duration_text) + '</span>';
          row.addEventListener('click', function () { play(v.id, v.title); });
          results.appendChild(row);
        });
      })
      .catch(function () { results.innerHTML = '<p class="muted">Search failed.</p>'; });
  }

  function play(id, title) {
    results.innerHTML = '<p class="muted">Resolving stream…</p>';
    fetch('webstream.php?action=resolve&id=' + encodeURIComponent(id))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        results.innerHTML = '';
        if (!data.ok || !data.stream) {
          results.innerHTML = '<p class="muted">Could not resolve this track.</p>';
          return;
        }
        player.style.display = '';
        document.getElementById('ptitle').textContent = data.title || title;
        document.getElementById('pmeta').textContent = (data.channel || '') + ' · ' + (data.duration_text || '');
        if (data.thumbnail) { document.getElementById('pthumb').src = data.thumbnail; }
        audio.src = data.stream;
        audio.play().catch(function () {});
      })
      .catch(function () { results.innerHTML = '<p class="muted">Resolve failed.</p>'; });
  }

  go.addEventListener('click', search);
  q.addEventListener('keydown', function (e) { if (e.key === 'Enter') { search(); } });
})();
</script>

<?php sh_footer(); ?>
