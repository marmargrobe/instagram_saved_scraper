## Instagram saved collections scraper (from html download)

  - [x] Update scrape_links script
  - [x] Create table for rawstd.insta_download_saved_reels_details
  - [x] update scrape_saved_posts
  - [ ] update scrape_saved_locations
  - [ ] see if more tables need to be added for those scripts - saved posts should fit into the saved reels table
  - [ ] Go to data cleaner and add these objects in the intial data collection portion
  - [ ] figure out how to run the cleaner files efficiently and without having to leave my computer on
  - [ ] add list of ip's that fail and add to antooher proxy file, update proxy function logic to ignore these ip's


---

### **Steps to Backup a PostgreSQL Database from AWS RDS**

1. **Create a Backup Using `pg_dump`**

   First, use the `pg_dump` command to create a backup of your PostgreSQL database. This command will allow you to create a `.dump` or `.sql` file of your database, which you can then download and transfer to your external hard drive.

   Here’s how to do it:

   - **Open your terminal** (if you’re using Windows, you can use Git Bash or any terminal emulator).
   - **Run the `pg_dump` command**:
   
     ```bash
     pg_dump -h <rds-endpoint> -U <your-username> -W -F c <database-name> -f backup.dump
     ```

     - Replace `<rds-endpoint>` with your RDS database's endpoint (e.g., `your-db-name.xxxxxxxx.us-east-1.rds.amazonaws.com`).
     - Replace `<your-username>` with the username you use to connect to the PostgreSQL database.
     - Replace `<database-name>` with the name of the database you want to back up.
     - The `-F c` option specifies that the backup will be in the custom format, which is often easier to restore.
     - The `-f backup.dump` option specifies the name of the backup file.

     When you run this command, it will prompt you for your PostgreSQL password. After that, it will create a backup file named `backup.dump` in your current working directory.

   Example:

   ```bash
   pg_dump -h mydb.abc123.us-east-1.rds.amazonaws.com -U admin -W -F c mydatabase -f /path/to/backup/backup.dump
   ```

   This will create a `backup.dump` file in the specified path.

2. **Download the Backup File to Your Local Machine**

   If you ran the `pg_dump` command locally, the backup file will already be on your machine. However, if you ran it from an EC2 instance or another server, you can download it using `scp`:

   ```bash
   scp -i <your-ec2-key.pem> ec2-user@<ec2-instance-ip>:/path/to/backup/backup.dump /path/to/local/directory
   ```

   Replace `<your-ec2-key.pem>`, `<ec2-instance-ip>`, and `/path/to/backup/backup.dump` with the appropriate values.

3. **Transfer the Backup File to Your External Hard Drive**

   Once the backup file is on your local machine, you can move it to your external hard drive.

   **If you're using a graphical interface:**
   - Simply drag and drop the `backup.dump` file from your local system to the external hard drive.

   **Using the command line (Linux/macOS):**

   If you prefer using the terminal, you can use the `cp` (copy) command to transfer the file:

   ```bash
   cp /path/to/backup/backup.dump /path/to/external/harddrive/
   ```

   Replace `/path/to/backup/backup.dump` with the location of your backup file and `/path/to/external/harddrive/` with the mount point of your external hard drive.

4. **Verify the Backup on Your External Hard Drive**

   Once the file has been transferred, check that the backup file (`backup.dump`) is accessible on your external hard drive.

---

### **Optional: Restoring the Backup Locally**

If you'd like to restore the backup to a local PostgreSQL instance or a test database, you can use the `pg_restore` command.

For example:

```bash
pg_restore -h localhost -U <your-username> -d <database-name> /path/to/backup/backup.dump
```

- Replace `/path/to/backup/backup.dump` with the path to the backup file.
- Replace `<your-username>` and `<database-name>` with your local PostgreSQL username and database name.

---

### **Summary**

1. **Create a backup** using `pg_dump` from your local machine.
2. **Download** the backup file if necessary.
3. **Transfer the backup** file to your external hard drive.
4. Optionally, **restore the backup** locally for verification.

This should allow you to easily back up your PostgreSQL database from AWS RDS and store it on your external hard drive. Let me know if you need further details!

---