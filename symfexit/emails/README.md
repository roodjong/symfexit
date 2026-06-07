# Emails

In symfexit we have customized emails, and also emails per language. 

## Explanation

Until we have renamed the models, we are maintaining layout and template. (I know they are ambigous, feel free to rename them).

### Template

The `EmailTemplate.template` field contains the type of mail. Think about new member mail, password forget mail, acceptation email, etc.
Each template provides its own predefined data. I.e. a password forget mail, provides: firstname, email and the password reset url itself. Where the password reset url is required to be in the body and the others are optional.

You can think of the template as the content of the email

### Layout

The layout field determines the header and the footer of the email.
Layout also has an `EmailLayout.template` field, this field determines the given fields.
This gives the possibility to add more than just the base, that supplies site_url, logo_url, site_name, for now. 

You can think of the layout as the header and the footer, that wraps around the template.
Example use case is the default text at the bottom of a mail, like: this email is automatically send, if something is wrong, contact this email.

This field is variable as I can imagine, you want different "layouts" for member focusesed emails, support member focused emails or general emails.

### localization

Each layout and template can be localized with 1 language. This means that when in the send_email function the language is given, it will try to get that language (with region fallback, e.g., 'en-US' falls back to 'en'). If not found, it tries the wildcard "*" (fallback for all languages). If that's not found, it gets the default application language (with region fallback). Finally, if not found, it uses the hardcoded email template.

## Usage

To send a mail use `send_email`. Import it just as the Email type you want to send. Then create that mail object and pass it to the send_email function. i.e.

```
from symfexit.emails._templates.emails.password_request import PasswordResetEmail
from symfexit.emails._templates.render import send_email

send_email(
    PasswordResetEmail(
        {
            "firstname": user.first_name,
            "url": reset_url,
            "email": user.email,
        }
    ),
    recipient_list=[to_email],
    lang=user.language,
)
```

The `send_email` function retrieves the appropriate template from the database based on the specified language. It then renders the template using the context parameters you provided.
Finally, `send_email` wraps the rendered template with the associated layout (header/footer). 

### Creating a New Template Type

To create a new email template type:

1. Create a new class that extends `BodyTemplate` in `symfexit/emails/_templates/emails/`
2. Define the `code` and `label` class attributes
3. Create a TypedDict for the context (specifying required fields)
4. Define `subject_template`, `html_template`, and `text_template` with hardcoded defaults
5. Implement `get_input_context()` to specify which context variables are available and whether they're required
6. Register the new class in `EmailTemplateManager._registry` in `manager.py`

The hardcoded templates serve as fallbacks, ensuring emails can be sent even before customized versions are created in the database.

### Customizing Emails in Django Admin

To customize the hardcoded email templates:

1. **Create a Layout (optional)**: In Django admin, create an `EmailLayout` to define custom headers/footers. Give it a descriptive name for easy reference.

2. **Create Email Templates**: For each language you want to support, create an `EmailTemplate` object:
   - Select the template type (e.g., "Password Reset", "Membership Application")
   - Choose the language (or "*" for fallback)
   - Optionally associate it with a layout
   - Customize the subject and body using Django template syntax with double brackets `{{variable}}`
   - Fill in both HTML and text versions

3. Once saved in the database, all subsequent emails of that type will use your customized version instead of the hardcoded default.


