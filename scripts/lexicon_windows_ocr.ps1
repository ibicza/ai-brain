param([Parameter(Mandatory=$true)][string]$Queue, [int]$Limit=0)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[void][Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
[void][Windows.Storage.FileAccessMode,Windows.Storage,ContentType=WindowsRuntime]
[void][Windows.Storage.Streams.IRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
[void][Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
[void][Windows.Graphics.Imaging.SoftwareBitmap,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
[void][Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
[void][Windows.Media.Ocr.OcrResult,Windows.Foundation,ContentType=WindowsRuntime]
[void][Windows.Globalization.Language,Windows.Globalization,ContentType=WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.IsGenericMethod -and $_.GetGenericArguments().Count -eq 1
} | Select-Object -First 1
function Await-Result($Operation, [Type]$ResultType) {
    $asyncTask=$asTask.MakeGenericMethod($ResultType).Invoke($null,@($Operation))
    $asyncTask.GetAwaiter().GetResult()
}
$engine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('ru'))
if ($null -eq $engine) {throw 'Windows Russian OCR is unavailable'}
$jobs=Get-Content -LiteralPath $Queue -Raw -Encoding UTF8 | ConvertFrom-Json
$processed=0; $failed=0; $resumed=0
$utf8=[System.Text.UTF8Encoding]::new($false)
foreach ($job in $jobs) {
    if ($Limit -gt 0 -and $processed+$failed+$resumed -ge $Limit) {break}
    $imageHash=(Get-FileHash -LiteralPath $job.image -Algorithm SHA256).Hash.ToLowerInvariant()
    if (Test-Path -LiteralPath $job.output) {
        $previous=Get-Content -LiteralPath $job.output -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($previous.image_sha256 -ne $imageHash -or $previous.page_id -ne $job.page_id) {throw 'OCR cache identity mismatch'}
        $resumed++; continue
    }
    $stream=$null; $bitmap=$null
    try {
        $file=Await-Result ([Windows.Storage.StorageFile]::GetFileFromPathAsync($job.image)) ([Windows.Storage.StorageFile])
        $stream=Await-Result ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        $decoder=Await-Result ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap=Await-Result ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        if ($bitmap.PixelWidth -gt [Windows.Media.Ocr.OcrEngine]::MaxImageDimension -or
            $bitmap.PixelHeight -gt [Windows.Media.Ocr.OcrEngine]::MaxImageDimension) {throw 'OCR image exceeds maximum dimension'}
        $result=Await-Result ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        $lines=@($result.Lines | ForEach-Object {
            $ocrLine=$_
            @{text=$ocrLine.Text; words=@($ocrLine.Words | ForEach-Object {
                @{text=$_.Text; bbox_pixels=@($_.BoundingRect.X,$_.BoundingRect.Y,
                    ($_.BoundingRect.X+$_.BoundingRect.Width),($_.BoundingRect.Y+$_.BoundingRect.Height))}
            })}
        })
        $record=@{schema=1;page_id=$job.page_id;image_sha256=$imageHash;original_sha256=$job.original_sha256;
            pdf_page=$job.pdf_page;engine='Windows.Media.Ocr';language='ru';status='OCR_DRAFT_REQUIRES_REVIEW';
            training_admitted=$false;image=$job.image;pixel_size=@($bitmap.PixelWidth,$bitmap.PixelHeight);
            text=$result.Text;lines=$lines}
        $parentPath=[System.IO.Path]::GetDirectoryName($job.output)
        [void][System.IO.Directory]::CreateDirectory($parentPath)
        [System.IO.File]::WriteAllText($job.output,($record | ConvertTo-Json -Depth 10),$utf8)
        $processed++
    } catch {
        $failed++
        Write-Warning ($job.page_id+': '+$_.Exception.Message)
    } finally {
        if ($null -ne $bitmap) {$bitmap.Dispose()}
        if ($null -ne $stream) {$stream.Dispose()}
    }
    if (($processed+$failed+$resumed) % 100 -eq 0) {
        Write-Output ('OCR progress '+($processed+$failed+$resumed)+'/'+$jobs.Count+'; failures='+$failed)
    }
}
Write-Output (@{processed=$processed;failed=$failed;resumed=$resumed;queue=$jobs.Count} | ConvertTo-Json -Compress)
if ($failed -gt 0) {exit 1}
