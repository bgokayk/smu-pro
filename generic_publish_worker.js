#!/usr/bin/env node
/**
 * Generic Publish Worker — SMU V2.0
 *
 * Parametrik worker: --channel ile hangi kanal için çalışacağını alır.
 * Config'den kanal bilgilerini okur, tarayıcıyı otomatik başlatır/bağlanır.
 *
 * Kullanım:
 *   node generic_publish_worker.js --channel poster_loop_cinema
 *   node generic_publish_worker.js --channel sahnebaddiestr
 *
 * Ortam değişkenleri:
 *   GENERIC_QUEUE_PATH  — Kuyruk dosyası yolu (opsiyonel, config'den okunur)
 *   GENERIC_STATE_PATH  — State dosyası yolu (opsiyonel)
 *   GENERIC_DEBUG_PORT  — Debug port (opsiyonel, config'den okunur)
 */

const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// ── Config ────────────────────────────────────────────────────────────────

const ROOT = path.resolve(__dirname);
const CONFIG_FILE = path.join(ROOT, 'smu_config.json');

function loadConfig() {
    try {
        return JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf-8'));
    } catch (e) {
        console.error(`Config dosyası okunamadı: ${CONFIG_FILE}`, e.message);
        return {};
    }
}

function getChannelConfig(channelId) {
    const config = loadConfig();
    const channels = config.channels || {};
    return channels[channelId] || {};
}

// ── Tarayıcı Yönetimi ─────────────────────────────────────────────────────

async function getBrowser(channelId) {
    const channelConfig = getChannelConfig(channelId);
    const browserType = (channelConfig.browser || 'Chrome').toLowerCase();
    const debugPort = parseInt(process.env.GENERIC_DEBUG_PORT || channelConfig.debugPort || '9222', 10);

    let browser;
    try {
        // Önce mevcut bir tarayıcıya bağlanmayı dene
        browser = await puppeteer.connect({
            browserURL: `http://127.0.0.1:${debugPort}`,
            defaultViewport: null,
        });
        console.log(`[${channelId}] Mevcut tarayıcıya bağlanıldı (port: ${debugPort})`);
        return { browser, isNew: false };
    } catch (e) {
        console.log(`[${channelId}] Tarayıcı bulunamadı (port: ${debugPort}), yeni başlatılıyor...`);
    }

    // Yeni tarayıcı başlat
    const userDataDir = path.join(ROOT, 'browser-profiles', channelId);
    fs.mkdirSync(userDataDir, { recursive: true });

    const launchArgs = [
        `--remote-debugging-port=${debugPort}`,
        `--user-data-dir=${userDataDir}`,
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-extensions',
        '--disable-sync',
    ];

    if (browserType === 'edge') {
        // Edge için executable path
        const edgePaths = [
            'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
            'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
        ];
        const edgePath = edgePaths.find(p => fs.existsSync(p));
        if (edgePath) {
            browser = await puppeteer.launch({
                headless: false,
                executablePath: edgePath,
                args: launchArgs,
            });
            console.log(`[${channelId}] Edge başlatıldı (port: ${debugPort})`);
            return { browser, isNew: true };
        }
    }

    // Varsayılan Chrome
    browser = await puppeteer.launch({
        headless: false,
        args: launchArgs,
    });
    console.log(`[${channelId}] Chrome başlatıldı (port: ${debugPort})`);
    return { browser, isNew: true };
}

// ── Kuyruk Yönetimi ───────────────────────────────────────────────────────

function loadQueue(channelId) {
    const queuePath = process.env.GENERIC_QUEUE_PATH || '';
    if (queuePath && fs.existsSync(queuePath)) {
        try {
            const data = JSON.parse(fs.readFileSync(queuePath, 'utf-8'));
            return Array.isArray(data) ? data : (data.items || []);
        } catch (e) {
            console.error(`Kuyruk okunamadı: ${queuePath}`, e.message);
        }
    }

    // Fallback: queues/ klasöründeki en güncel dosyayı bul
    const queuesDir = path.join(ROOT, 'queues');
    if (!fs.existsSync(queuesDir)) return [];

    const files = fs.readdirSync(queuesDir)
        .filter(f => f.includes(channelId) && f.endsWith('.json'))
        .sort()
        .reverse();

    for (const file of files) {
        try {
            const data = JSON.parse(fs.readFileSync(path.join(queuesDir, file), 'utf-8'));
            const items = Array.isArray(data) ? data : (data.items || []);
            if (items.length > 0) {
                console.log(`[${channelId}] Kuyruk bulundu: ${file} (${items.length} öğe)`);
                return items;
            }
        } catch (e) {
            console.warn(`Kuyruk okunamadı: ${file}`, e.message);
        }
    }

    return [];
}

// ── Publish İşlemi ────────────────────────────────────────────────────────

async function publishToYouTube(page, item) {
    const title = item.youtubeTitle || item.title || 'Shorts';
    const description = item.youtubeDescription || '';
    const filePath = item.file || item.sourcePath || '';

    console.log(`[YouTube] Başlık: ${title}`);
    console.log(`[YouTube] Dosya: ${filePath}`);

    // YouTube Studio'ya git
    await page.goto('https://studio.youtube.com', { waitUntil: 'networkidle2', timeout: 30000 });
    await page.waitForTimeout(3000);

    // "Oluştur" butonuna tıkla
    try {
        const createBtn = await page.$('ytcp-button#create-icon');
        if (createBtn) {
            await createBtn.click();
            await page.waitForTimeout(2000);
        }
    } catch (e) {
        console.warn('Oluştur butonu bulunamadı, devam ediliyor...');
    }

    // "Video yükle" seçeneğine tıkla
    try {
        const uploadBtn = await page.$('ytcp-ve[aria-label="Video yükle"]');
        if (uploadBtn) {
            await uploadBtn.click();
            await page.waitForTimeout(2000);
        }
    } catch (e) {
        console.warn('Video yükle butonu bulunamadı');
    }

    // Dosya seç
    if (filePath && fs.existsSync(filePath)) {
        try {
            const fileInput = await page.$('input[type="file"]');
            if (fileInput) {
                await fileInput.uploadFile(filePath);
                console.log(`[YouTube] Dosya yüklendi: ${filePath}`);
                await page.waitForTimeout(5000);
            }
        } catch (e) {
            console.error('Dosya yükleme hatası:', e.message);
        }
    }

    // Başlık gir
    try {
        const titleInput = await page.$('#title-textarea');
        if (titleInput) {
            await titleInput.click();
            await page.waitForTimeout(500);
            // Mevcut metni temizle
            await titleInput.click({ clickCount: 3 });
            await page.keyboard.press('Backspace');
            await page.waitForTimeout(300);
            await titleInput.type(title, { delay: 50 });
            console.log(`[YouTube] Başlık girildi: ${title}`);
        }
    } catch (e) {
        console.warn('Başlık girişi hatası:', e.message);
    }

    // Açıklama gir
    if (description) {
        try {
            const descInput = await page.$('#description-textarea');
            if (descInput) {
                await descInput.click();
                await page.waitForTimeout(300);
                await descInput.type(description, { delay: 20 });
                console.log(`[YouTube] Açıklama girildi`);
            }
        } catch (e) {
            console.warn('Açıklama girişi hatası:', e.message);
        }
    }

    // "Shorts" seçeneğini işaretle
    try {
        const shortsRadio = await page.$('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_TYPE"]');
        if (shortsRadio) {
            // Shorts için gerekli ayarlar
        }
    } catch (e) {
        // Önemsiz
    }

    // Yayınla
    try {
        const nextBtn = await page.$('ytcp-button#next-button');
        if (nextBtn) {
            await nextBtn.click();
            await page.waitForTimeout(2000);
        }
    } catch (e) {
        console.warn('İleri butonu bulunamadı');
    }

    // İkinci adım (görünürlük)
    try {
        const nextBtn2 = await page.$('ytcp-button#next-button');
        if (nextBtn2) {
            await nextBtn2.click();
            await page.waitForTimeout(2000);
        }
    } catch (e) {
        console.warn('İleri butonu (2) bulunamadı');
    }

    // Üçüncü adım (kontrol)
    try {
        const nextBtn3 = await page.$('ytcp-button#next-button');
        if (nextBtn3) {
            await nextBtn3.click();
            await page.waitForTimeout(2000);
        }
    } catch (e) {
        console.warn('İleri butonu (3) bulunamadı');
    }

    // Yayınla
    try {
        const publishBtn = await page.$('ytcp-button#done-button');
        if (publishBtn) {
            await publishBtn.click();
            console.log(`[YouTube] Yayınlandı: ${title}`);
            await page.waitForTimeout(5000);
            return true;
        }
    } catch (e) {
        console.warn('Yayınla butonu bulunamadı');
    }

    return false;
}

// ── Ana İşlem ─────────────────────────────────────────────────────────────

async function main() {
    const args = process.argv.slice(2);
    const channelIndex = args.indexOf('--channel');
    const channelId = channelIndex >= 0 ? args[channelIndex + 1] : '';

    if (!channelId) {
        console.error('Kanal adı gerekli: --channel poster_loop_cinema');
        process.exit(1);
    }

    console.log(`\n=== Generic Publish Worker: ${channelId} ===\n`);

    // Kuyruğu yükle
    const queue = loadQueue(channelId);
    if (queue.length === 0) {
        console.log(`[${channelId}] Kuyruk boş, işlem yapılmadı.`);
        return;
    }

    console.log(`[${channelId}] ${queue.length} öğe bulundu.`);

    // Tarayıcıyı başlat/bağlan
    const { browser, isNew } = await getBrowser(channelId);
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 800 });

    // Her öğeyi yayınla
    let published = 0;
    for (const item of queue) {
        console.log(`\n--- İşleniyor: ${item.id || item.youtubeTitle || 'bilinmeyen'} ---`);

        const success = await publishToYouTube(page, item);
        if (success) {
            published++;
            // Published Registry'ye kaydet (Python script ile)
            try {
                const contentId = item.id || item.queueItemId || '';
                if (contentId) {
                    execSync(`python published_registry.py mark --channel ${channelId} --content-id ${contentId}`, {
                        cwd: ROOT,
                        stdio: 'ignore',
                    });
                    console.log(`[Registry] Kaydedildi: ${contentId}`);
                }
            } catch (e) {
                console.warn('Registry kaydı başarısız:', e.message);
            }
        }
    }

    // Tarayıcıyı kapat
    if (isNew) {
        await browser.close();
        console.log(`[${channelId}] Tarayıcı kapatıldı.`);
    } else {
        await page.close();
        await browser.disconnect();
        console.log(`[${channelId}] Tarayıcı bağlantısı kesildi.`);
    }

    console.log(`\n=== ${channelId} tamamlandı: ${published}/${queue.length} yayınlandı ===\n`);
}

main().catch(err => {
    console.error('Kritik hata:', err);
    process.exit(1);
});
