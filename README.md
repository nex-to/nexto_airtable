### Prerequisites:
1.  Add cron_status column to Airtable *Requests* table.

2.  Add cron_status_calc column to Airtable *Requests* table.

3.  Enter the formula **IF({cron_status} = BLANK(), 0, {cron_status})** for cron_status_calc column.

4.  Set the cron_status_cal column in the *Requests* table to -1 for the records that the cron job should
    should ignore the first time it runs.
    


### To install and configure this odoo module:

1.  Create a directory in the *addons* folder of your odoo installation.

2.  Place the contents of this module in the directory you created in step 1.

3.  Run **odoo-bin --addons-path=addons --database=*odoo_db_name***

4.  Navigate to the *Settings* page in odoo and click on *NexTo Airtable*

5.  Enter values for all of the fields and *Save*

6.  Navigate to *Scheduled Actions* under *Automation* of *Technical settings*.

7.  Click on the *Action Name* ***NexTo: Airtable Insert Delivery Items on Delivery Request***

8.  Click on *Edit*.

9.  Set the *Active* flag to true.

10. Adjust other values as needed.

11.  In the Python Code section enter the parameter for the *model._insert_delivery_items_on_delivery_request()* method call.  
    The parameter value is the Distributor ID for which you want the cron job to run.  The value can be found in the 
    ***RecordId_Calc*** column of the *Neighbor Express Entities* table in Airtable.

12.  Click *Save*.

13.  Repeat steps 8, 9, 10, 11, and 12 for the *Action Name* ***NexTo: Airtable Insert Inventory Log on Delivery Request Completion***.
