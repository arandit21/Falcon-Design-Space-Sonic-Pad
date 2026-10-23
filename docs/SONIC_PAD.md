# Служба Falcon A1 на Creality Sonic Pad

Windows-установщик 1.3.0 выполняет эти действия при первоначальной настройке. Ручная установка нужна, если служба требуется отдельно или нужна диагностика.

## Состав

- `/etc/falcon_a1/bridge_r3.py` — точный диагностический мост **R4**. Историческое имя сохранено для совместимости.
- `/etc/falcon_a1/service_control.py` — управление только собственным процессом.
- `/etc/init.d/falcon_a1_bridge` — служба Sonic Pad/OpenWrt.
- `/etc/rc.d/S99falcon_a1_bridge` — ссылка автозапуска.
- `/tmp/falcon_sonic_pad_r4.log` — журнал новой службы.

R4 не выполняет задания и не двигает станок. В новой установке HTTP доступен только на `127.0.0.1:18765`: `/health`, `/device`, `/id`. Последние два адреса читают идентификатор и состояние контроллера. Нативный ретранслятор использует loopback-порты `18921/18922`: Windows запускает его через SSH, временно останавливает R4 и возвращает службу после завершения. Watchdog завершает ретранслятор при потере сеанса; это не гарантия немедленной физической остановки уже принятого контроллером задания.

## Требования

Root-доступ по SSH, Python **3.7+**, `ffmpeg`, `sha256sum`, `/etc/rc.common`. Контроллер A1: USB `303a:4001`, камера: `1bcf:0b19`. Служба не меняет Klipper, прошивку, сетевые настройки или пароль Pad.

## Перенос файлов из Windows

Распакуйте `Falcon_SonicPad_Service_1.3.0.zip`. Откройте PowerShell в папке с `install_service.py`. Укажите настоящий IP вместо примера:

```powershell
$PadAddress = "192.168.1.36"
$SshCompat = @("-oHostKeyAlgorithms=+ssh-rsa", "-oPubkeyAcceptedAlgorithms=ssh-rsa", "-oMACs=+hmac-sha1")
ssh @SshCompat "root@$PadAddress" "mkdir -p /mnt/UDISK/falcon_sonicpad_service"
scp -O @SshCompat .\falcon_a1_bridge_r4.py .\service_control.py .\falcon_a1_bridge.init .\install_service.py .\sonic_native.sh .\sonic_serial_relay.py .\sonic_camera_photo.py "root@${PadAddress}:/mnt/UDISK/falcon_sonicpad_service/"
ssh @SshCompat "root@$PadAddress"
```

При первом соединении проверьте отпечаток своего Pad и введите пароль в запросе SSH. `scp -O` нужен устройствам со старым SCP без SFTP. Универсального root-пароля в инструкции нет.

## На Sonic Pad

Эти команды выполняются **в SSH-консоли Pad**, не в PowerShell:

```sh
cd /mnt/UDISK/falcon_sonicpad_service
python3 install_service.py check
```

После `CHECK PASSED`:

```sh
python3 install_service.py install
/etc/init.d/falcon_a1_bridge status
wget -qO- http://127.0.0.1:18765/health
```

Ожидаются `running` и `Falcon A1 Bridge R4`. `/health` не открывает последовательный порт. Пока работает FDS с нативным ретранслятором, R4 временно остановлен — это нормально.

Установщик сохраняет уже установленную точную R4 и её регистрацию. Если обнаружен старый R3 или неизвестная служба, установка прервётся; чужие процессы не завершаются. Унаследованная R4 может слушать локальную сеть по прежним настройкам: её адрес не меняется.

## Управление и автозапуск

Закройте FDS перед ручным управлением службой:

```sh
/etc/init.d/falcon_a1_bridge status
/etc/init.d/falcon_a1_bridge stop
/etc/init.d/falcon_a1_bridge start
```

Автозапуск включён ссылкой `S99falcon_a1_bridge`. Перезагрузка для установки не требуется. Новая регистрация автозапуска проверена изолированно, но пока не подтверждена на сброшенном устройстве — [статус проверок](ПРОВЕРКИ.md).

## Удаление

Закройте FDS:

```sh
cd /mnt/UDISK/falcon_sonicpad_service
python3 install_service.py uninstall
```

Удаляются только управляемый процесс, init-скрипт и ссылка автозапуска с маркером этого пакета. Файлы в `/etc/falcon_a1` остаются. Унаследованная служба без маркера не удаляется. Штатные службы и список SSH-ключей не затрагиваются.

## Если контроллер не виден

```sh
ls -l /dev/ttyACM* /dev/ttyUSB*
dmesg | tail -40
python3 --version
command -v ffmpeg
```

Камера определяется независимо от A1. Если есть только Creality Falcon Camera, проверьте питание A1, USB-кабель, разъём и хаб.
