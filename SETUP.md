# Telemetry laptop setup (Ubuntu, InfluxDB and Grafana)

_How to build a telemetry laptop from scratch: a fresh Ubuntu install with InfluxDB 1.x, Grafana and the telemetry receiver. Written for people who are technical but new to Linux. Once this is done, follow the race-day steps in the [README](README.md#how-to-run-telemetry-race-day)._

## What you will end up with

```
 XBee radio (USB)  →  /dev/ttyUSB0
   ▼
 Ubuntu (a dedicated laptop, or a VirtualBox virtual machine)
   ├── telemetry receiver (Python, this repository)
   ├── InfluxDB 1.x      database, port 8086, database "DUSCiESC"
   └── Grafana           dashboards in a web browser, port 3000
```

Everything runs on one machine, and needs no internet connection once it is set up.

## Choose: dedicated laptop or virtual machine

| | Dedicated laptop running Ubuntu | VirtualBox virtual machine (VM) |
|---|---|---|
| What it is | Ubuntu installed directly on a laptop (replacing, or alongside, Windows) | Ubuntu running in a window on your normal Windows, macOS or Linux computer |
| Good for | Race day: simplest and most reliable | Trying it out, development, testing, or when you only have one laptop |
| USB serial (XBee) | Works directly | Must be passed through from the host to the VM ([Part 2](#part-2-pass-the-xbee-usb-through-to-the-vm)) |
| Start at | [Part 3](#part-3-prepare-ubuntu) (after installing Ubuntu) | [Part 1](#part-1-create-the-virtualbox-vm) |

**Which Ubuntu?** Use the current **Ubuntu Desktop LTS** release (long term support, e.g. 24.04 LTS) from <https://ubuntu.com/download/desktop>. Ubuntu variants work the same way: **Xubuntu** or **Lubuntu** use less memory and suit older laptops and VMs. Every command in this guide works on all of them.

## A few Linux basics first

| You will see | What it means |
|---|---|
| **Terminal** | The command line. Open it with **Ctrl+Alt+T**, or search for "Terminal". Commands in this guide are typed (or pasted) there and run with Enter |
| Pasting into the terminal | **Ctrl+Shift+V** (plain Ctrl+V does not work in the terminal). Copy with **Ctrl+Shift+C** |
| `sudo <command>` | Run a command as administrator. It asks for **your own** password. Nothing appears on screen while you type the password: that is normal |
| `apt` / `apt-get` | Ubuntu's package (software) manager, like an app store for the command line. `sudo apt update` refreshes the list of software; `sudo apt install <name>` installs something |
| `systemctl` | Controls **services**: programs that run in the background and start automatically at boot (InfluxDB and Grafana are services). `status` shows whether one is running; press **q** to get back to the prompt |
| `nano <file>` | A simple text editor in the terminal. Save with **Ctrl+O** then Enter, exit with **Ctrl+X** |
| `~` | Your home folder, e.g. `/home/yourname` |
| `/dev/ttyUSB0` | The USB serial port the XBee appears as. In Linux, devices appear as files under `/dev` |
| Ctrl+C | Stop the program running in the terminal |

If a command prints an error, read the last few lines: they usually say what went wrong. See [Troubleshooting](#troubleshooting) at the end.

---

## Part 1: Create the VirtualBox VM

_Skip to [Part 3](#part-3-prepare-ubuntu) if you installed Ubuntu directly on the laptop._

### 1.1 Install VirtualBox

1. Download **VirtualBox 7** (or later) for your computer from <https://www.virtualbox.org/wiki/Downloads> and install it.
   * **Windows:** accept the prompts to install the device drivers (including the USB driver). These are needed for USB passthrough.
   * **Linux host:** add yourself to the `vboxusers` group, then log out and back in, or VirtualBox cannot see USB devices:
     ```shell
     sudo usermod -aG vboxusers $USER
     ```
   * **Mac with Apple silicon (M1 and later):** VirtualBox support is newer and needs the ARM64 version of Ubuntu. If you have trouble, use a Windows or Linux computer instead.
2. You do **not** need the VirtualBox Extension Pack: since VirtualBox 7.0 the USB 2.0 and 3.0 controllers are included. (On the older VirtualBox 6, USB 2.0/3.0 needs the Extension Pack, which has its own licence terms.)

### 1.2 Download Ubuntu

Download the Ubuntu Desktop LTS `.iso` file (about 6 GB) from <https://ubuntu.com/download/desktop>. Don't open it: VirtualBox uses it as a virtual DVD.

### 1.3 Create the VM

1. In VirtualBox, click **New**.
2. **Name:** `telemetry`. **ISO Image:** choose the Ubuntu `.iso` you downloaded. **Type:** Linux, **Version:** Ubuntu (64-bit).
3. Tick **Skip Unattended Installation**. You will install Ubuntu yourself in a moment, which avoids problems with the automatically created user account.
4. **Hardware:** at least **4096 MB** memory and **2** processors.
5. **Hard disk:** create a virtual hard disk of at least **30 GB**. It only takes up space on your computer as it fills.
6. Click **Finish**.

### 1.4 Adjust the VM settings

Select the VM and click **Settings**:

* **USB:** tick **Enable USB Controller** and choose **USB 3.0 (xHCI) Controller**. (If the XBee doesn't work later, try **USB 2.0 (EHCI)** instead.)
* **Network:**
  * **NAT** (the default) is enough: the VM can reach the internet, and you use Grafana from a browser inside the VM.
  * Choose **Bridged Adapter** instead if other computers on the telemetry network need to open Grafana. The VM then gets its own address on the network, like a separate computer.
* **Display:** set **Video Memory** to 128 MB.

### 1.5 Install Ubuntu in the VM

1. Click **Start**. The VM boots from the Ubuntu `.iso`.
2. Choose **Install Ubuntu** and follow the installer. When asked how to install, **Erase disk and install Ubuntu** is safe: it only erases the VM's empty virtual disk, not your computer's.
3. Create your user account and remember the password: you need it for `sudo`.
4. When it finishes, restart the VM. If it asks you to remove the installation medium, just press Enter.

### 1.6 Install the VirtualBox Guest Additions (recommended)

These make the VM window resizable, keep the VM's clock in sync, and let you copy and paste between your computer and the VM.

1. In the VM, open a terminal and install the tools needed to build them:
   ```shell
   sudo apt update
   sudo apt install -y build-essential bzip2
   ```
2. In the VirtualBox menu of the VM window, choose **Devices → Insert Guest Additions CD image**. When Ubuntu offers to run it, choose **Run**, or run it from the terminal:
   ```shell
   sudo sh /media/$USER/VBox_GAs_*/VBoxLinuxAdditions.run
   ```
3. Restart the VM.
4. Choose **Devices → Shared Clipboard → Bidirectional**, so you can copy commands from this guide on your computer and paste them into the VM's terminal (with Ctrl+Shift+V).

---

## Part 2: Pass the XBee USB through to the VM

_Skip this part on a dedicated laptop._

A USB device can be used by your computer (the **host**) or by the VM, not both at once. Passing it through hands it over to the VM, where it appears as `/dev/ttyUSB0`, just as on a real Linux laptop.

### 2.1 Attach it once (manual)

1. Start the VM and log in.
2. Plug the XBee into your computer.
3. In the VM window's menu, choose **Devices → USB**, and click the XBee's USB adapter to tick it. It usually shows up as something like **FTDI FT231X USB UART** or **FTDI FT232R USB UART**, depending on the adapter.
4. Check that the VM can see it (in the VM's terminal):
   ```shell
   ls /dev/ttyUSB*
   ```
   You should see `/dev/ttyUSB0`. If you are not sure which device in the list is the XBee, unplug it, look at the list again, and see which one disappears.

### 2.2 Attach it automatically (USB filter)

To avoid ticking the device every time:

1. Shut down the VM, or leave it running and plug the XBee in.
2. Open the VM's **Settings → USB**.
3. Click the **Add new USB filter** icon (a USB plug with a green **+**) and choose the XBee's adapter from the list.
4. Click **OK**.

From now on, whenever the VM is running and the XBee is plugged in, it goes straight to the VM. Do the same for the **Arduino Mega** (it shows up as `/dev/ttyACM0` in the VM) if you want to program the telemetry board from the VM (see [Telemetry/README.md](Telemetry/README.md)).

If the device is greyed out in the **Devices → USB** menu, a program on your computer is using it (e.g. XCTU, the Arduino IDE or a serial monitor). Close that program and try again. On a Linux host, check that you are in the `vboxusers` group (step 1.1).

---

## Part 3: Prepare Ubuntu

_From here on, the steps are the same for a dedicated laptop and a VM. Run all the commands in a terminal on the Ubuntu machine._

1. Bring Ubuntu up to date, then restart:
   ```shell
   sudo apt update && sudo apt upgrade -y
   sudo reboot
   ```
2. Install the tools the telemetry code needs:
   ```shell
   sudo apt install -y git python3-venv python3-pip curl wget gnupg
   ```
3. Give your user access to serial ports. Without this, the receiver fails with `Permission denied: '/dev/ttyUSB0'`:
   ```shell
   sudo usermod -aG dialout $USER
   ```
   **Log out and back in** (or restart) for this to take effect. Afterwards, `groups` should list `dialout`.
4. Remove `brltty`. It is a driver for braille displays that some USB serial adapters are mistaken for: it grabs the adapter, and `/dev/ttyUSB0` appears for a moment and then disappears.
   ```shell
   sudo apt remove -y brltty
   ```
5. Optional, but recommended on a dedicated telemetry machine: stop ModemManager. It probes new serial ports in case they are mobile broadband modems, which can interfere with the XBee for the first few seconds after it is plugged in.
   ```shell
   sudo systemctl disable --now ModemManager
   ```
   (Leave it enabled if the machine also uses a mobile broadband modem.)

---

## Part 4: Install InfluxDB 1.x

The receiver uses **InfluxDB 1.x** (and its InfluxQL query language). InfluxDB 2.x and 3.x work differently and are **not** compatible with it, so make sure you install the 1.x package called `influxdb`, as below, not `influxdb2`.

These steps follow the official InfluxData instructions at <https://docs.influxdata.com/influxdb/v1/introduction/install/>. If a step below fails, check that page in case InfluxData has changed something (e.g. its signing key).

1. Download InfluxData's signing key. This lets Ubuntu check that the software really comes from InfluxData:
   ```shell
   cd /tmp
   wget -q https://repos.influxdata.com/influxdata-archive.key
   gpg --show-keys --with-fingerprint --with-colons ./influxdata-archive.key | grep fpr
   ```
   The first `fpr` line must contain **`24C975CBA61A024EE1B631787C3D57159FC2F927`**. If it does not, stop and check the InfluxData page.
2. Install the key and add InfluxData's software repository:
   ```shell
   sudo mkdir -p /etc/apt/keyrings
   gpg --dearmor < influxdata-archive.key | sudo tee /etc/apt/keyrings/influxdata-archive.gpg > /dev/null
   echo 'deb [signed-by=/etc/apt/keyrings/influxdata-archive.gpg] https://repos.influxdata.com/debian stable main' | sudo tee /etc/apt/sources.list.d/influxdata.list
   ```
3. Install InfluxDB, and set it up as a **service that starts automatically at every boot**:
   ```shell
   sudo apt update
   sudo apt install -y influxdb
   sudo systemctl unmask influxdb.service
   sudo systemctl enable --now influxdb
   ```
   `enable` makes it start at boot; `--now` also starts it straight away.
4. Check it is running, and set to start at boot:
   ```shell
   systemctl status influxdb               # should say "active (running)"; press q to exit
   systemctl is-enabled influxdb           # should say "enabled"
   curl -sl -I http://localhost:8086/ping  # should say "HTTP/1.1 204 No Content"
   ```
5. Create the database the receiver writes to (its name is set in [Receiver/receiver_config.py](Receiver/receiver_config.py)):
   ```shell
   influx -execute 'CREATE DATABASE "DUSCiESC"'
   influx -execute 'SHOW DATABASES'        # DUSCiESC should be listed
   ```

**About passwords.** InfluxDB 1.x has authentication **turned off** by default, so it accepts any user name and password, including the `admin` / `password` in `receiver_config.py`. That is fine on a closed telemetry network. To turn authentication on:
1. Create a user with `influx -execute "CREATE USER admin WITH PASSWORD '<a password>' WITH ALL PRIVILEGES"`.
2. Set `auth-enabled = true` in the `[http]` section of `/etc/influxdb/influxdb.conf` (`sudo nano /etc/influxdb/influxdb.conf`), then `sudo systemctl restart influxdb`.
3. Put the same password in `Receiver/receiver_config.py` and in the Grafana data source below.

InfluxDB keeps its data in `/var/lib/influxdb`.

---

## Part 5: Install Grafana

Grafana draws the live dashboards in a web browser. These steps follow the official Grafana instructions at <https://grafana.com/docs/grafana/latest/setup-grafana/installation/debian/>.

1. Add Grafana's signing key and software repository:
   ```shell
   sudo apt install -y apt-transport-https wget gnupg
   sudo mkdir -p /etc/apt/keyrings
   sudo wget -O /etc/apt/keyrings/grafana.asc https://apt.grafana.com/gpg-full.key
   sudo chmod 644 /etc/apt/keyrings/grafana.asc
   echo "deb [signed-by=/etc/apt/keyrings/grafana.asc] https://apt.grafana.com stable main" | sudo tee /etc/apt/sources.list.d/grafana.list
   ```
2. Install Grafana (the free, open source edition), and set it up as a **service that starts automatically at every boot**. Unlike InfluxDB, Grafana's package does not do this by itself, so the `enable` step matters:
   ```shell
   sudo apt update
   sudo apt install -y grafana
   sudo systemctl daemon-reload
   sudo systemctl enable --now grafana-server
   systemctl status grafana-server         # should say "active (running)"; press q to exit
   systemctl is-enabled grafana-server     # should say "enabled"
   ```
3. Open a web browser on the Ubuntu machine and go to <http://localhost:3000>. Log in with user **admin**, password **admin**, and choose a new password when asked. (With a bridged VM or a laptop on the telemetry network, other computers can use `http://<ubuntu machine's IP address>:3000`; find the address with `hostname -I`.)
4. Connect Grafana to InfluxDB:
   1. In the menu, go to **Connections → Data sources → Add data source**, and choose **InfluxDB**.
   2. **Query language:** InfluxQL.
   3. **URL:** `http://localhost:8086`
   4. **Database:** `DUSCiESC`
   5. **User** and **Password:** leave empty, or enter the ones from Part 4 if you turned authentication on.
   6. Click **Save & test**. It should report that the data source is working.
5. Add the telemetry dashboard. The Peri Grafana dashboard is **not** stored in this repository:
   * If you have an exported copy (a `.json` file), go to **Dashboards → New → Import** and upload it.
   * Otherwise, build panels with **Dashboards → New → New dashboard → Add visualization**. Choose the InfluxDB data source, switch the query editor to raw mode (the pencil icon), and enter a query such as:
     ```
     SELECT "VehicleVelocity" FROM "Tritium/Velocity" WHERE $timeFilter
     ```
     [dbc/SIGNALS.md](dbc/SIGNALS.md) lists every measurement and field you can plot, with its unit.

   Once you have a working dashboard, export it as a JSON file (the dashboard's **Export** button, or **Share → Export** in older Grafana versions) and keep a copy safe, so the next laptop can import it.

---

## Part 6: Install the telemetry code

The code is cloned over **SSH**, so that changes made on this machine can be committed and pushed back to GitHub. SSH uses a key pair instead of a password: a private key that stays on this machine, and a public key you give to GitHub. You need a GitHub account with write access to [DUEM/Telemetry2021](https://github.com/DUEM/Telemetry2021) (ask the team).

1. Tell git who you are. This name and email are recorded on every commit you make:
   ```shell
   git config --global user.name "Your Name"
   git config --global user.email "you@example.com"
   ```
2. Create an SSH key for this machine (skip this if `ls ~/.ssh/id_ed25519.pub` already shows one):
   ```shell
   ssh-keygen -t ed25519 -C "you@example.com"
   ```
   Press Enter to accept the default file location. Then either type a passphrase (protects the key if the laptop is lost or shared; Ubuntu remembers it after the first use) or press Enter twice for none.
3. Show the **public** key and copy all of it (one line, starting `ssh-ed25519`):
   ```shell
   cat ~/.ssh/id_ed25519.pub
   ```
   Never share the private key, `~/.ssh/id_ed25519` (the file without `.pub`).
4. Add the public key to GitHub: on <https://github.com>, go to your profile picture → **Settings → SSH and GPG keys → New SSH key**. Give it a title naming this machine (e.g. `telemetry VM`), paste the key, and click **Add SSH key**.
5. Check that GitHub accepts the key:
   ```shell
   ssh -T git@github.com
   ```
   The first time, it asks whether to trust GitHub's host key: type `yes`. It should then reply `Hi <your user name>! You've successfully authenticated, but GitHub does not provide shell access.` (that last part is normal).
6. Get the code:
   ```shell
   cd ~
   git clone -b PERI-DEVELOPMENT-TPB-1126 --recurse-submodules git@github.com:DUEM/Telemetry2021.git
   cd Telemetry2021
   ```
   The CANApi submodule (the firmware's CAN library) is cloned over SSH too, using the same key.
7. Create a Python virtual environment and install the receiver's packages into it. A virtual environment is a private folder of Python packages for this project. Ubuntu does not let `pip` install into the system Python.
   ```shell
   python3 -m venv ~/virtualenvs/telemetry
   source ~/virtualenvs/telemetry/bin/activate
   pip install -r Receiver/requirements.txt
   ```
   Your prompt now starts with `(telemetry)`. Run the `source` line again in every new terminal before running the receiver.
8. Check everything works by running the tests:
   ```shell
   pip install -r Tests/requirements-test.txt
   pytest
   ```
   The last line should say that all tests **passed**.

---

## Part 7: Check it end to end, without the car

You can send a recorded capture through a pair of virtual serial ports, and watch it arrive in InfluxDB and Grafana. This writes the sample data into the `DUSCiESC` database.

1. Install `socat`, a tool that creates virtual serial ports:
   ```shell
   sudo apt install -y socat
   ```
2. Follow the **Live replay** steps in [Receiver/README.md](Receiver/README.md#testing-without-hardware). You need three terminals: one for `socat`, one for the receiver, and one to send the capture.
3. Check the data arrived:
   ```shell
   influx -database DUSCiESC -execute 'SHOW MEASUREMENTS'
   ```
4. In Grafana, look at a panel. Set the **time range** (top right) to include **22 March 2024**: the sample capture's timestamps come from the GPS in the recording, not from today's date.

If you want an empty database again afterwards, delete and recreate it:

```shell
influx -execute 'DROP DATABASE "DUSCiESC"'
influx -execute 'CREATE DATABASE "DUSCiESC"'
```

---

## After a restart

InfluxDB and Grafana run as services, so they start automatically every time Ubuntu boots: there is nothing to start by hand. Check this once after setting up, by restarting and then running:

```shell
systemctl is-active influxdb grafana-server     # should print "active" twice
```

If either says `inactive` or `failed`, run `sudo systemctl enable --now influxdb grafana-server` and see [Troubleshooting](#troubleshooting).

To run telemetry:

1. (VM only) Start the VM. With the USB filter from [Part 2](#22-attach-it-automatically-usb-filter), the XBee is passed through as soon as it is plugged in.
2. Follow the race-day steps in the [README](README.md#how-to-run-telemetry-race-day).

---

## Troubleshooting

| Problem | What to check |
|---|---|
| `ls /dev/ttyUSB*` shows nothing | VM: is the XBee ticked under **Devices → USB**? Is the host using it ([Part 2](#part-2-pass-the-xbee-usb-through-to-the-vm))? Run `sudo dmesg \| tail -20` straight after plugging it in to see what Linux made of it |
| `/dev/ttyUSB0` appears then disappears | `brltty` has grabbed it: `sudo apt remove brltty` ([Part 3](#part-3-prepare-ubuntu), step 4) |
| `Permission denied: '/dev/ttyUSB0'` | You are not in the `dialout` group yet: run step 3 of [Part 3](#part-3-prepare-ubuntu), then log out and back in |
| XBee greyed out in VirtualBox's **Devices → USB** menu | A program on the host has it open (close XCTU, the Arduino IDE or serial monitors). On a Linux host, check you are in `vboxusers` |
| The XBee works in the VM but no data arrives | Is the car's telemetry board powered and transmitting? Is the baud rate 115200 (see [Receiver/README.md](Receiver/README.md#configuration))? Try the other USB controller type in the VM settings (USB 2.0 instead of 3.0) |
| `curl ... /ping` fails, or `influx` says connection refused | `systemctl status influxdb`. To see its log: `journalctl -u influxdb -n 50` |
| Grafana does not load at `http://localhost:3000` | `systemctl status grafana-server`, and `journalctl -u grafana-server -n 50` |
| Grafana **Save & test** fails | Check the URL is `http://localhost:8086`, the query language is InfluxQL, and the database `DUSCiESC` exists (`influx -execute 'SHOW DATABASES'`) |
| A Grafana panel shows "No data" | Most often the **time range**: check it covers the time the data was recorded. Then check the measurement name in double quotes, e.g. `"Tritium/Velocity"`, exactly as in [dbc/SIGNALS.md](dbc/SIGNALS.md) |
| The receiver logs `Influx rejected write` | Read the message: `database not found` means create the database (Part 4, step 5); `field type conflict` means a field changed type, see [dbc/README.md](dbc/README.md#changing-or-adding-a-message-or-signal) |
| `git clone` or `ssh -T git@github.com` says `Permission denied (publickey)` | GitHub does not have this machine's public key: repeat steps 3 and 4 of [Part 6](#part-6-install-the-telemetry-code), making sure you copied the whole `.pub` line. `ssh -vT git@github.com` shows which key files it tries |
| `git push` says `Permission to DUEM/Telemetry2021.git denied` | Your GitHub account can read the repository but not write to it: ask the team for write access |
| InfluxDB or Grafana not running after a restart | `systemctl is-enabled influxdb grafana-server` should print `enabled` twice. If not: `sudo systemctl enable --now influxdb grafana-server` |
| `pip install` fails with `externally-managed-environment` | The virtual environment is not active: run `source ~/virtualenvs/telemetry/bin/activate` first |
| `apt` says another process is using it (`Could not get lock`) | Ubuntu is installing updates in the background. Wait a few minutes and try again |
