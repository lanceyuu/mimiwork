"""Preparing one email for the screen."""

from __future__ import annotations

import base64
from email.message import EmailMessage

from mail_fakes import mail

from coworker.mail import render
from coworker.mail.render import render_message

PNG = b"\x89PNG-not-really"


def _with_inline_image(payload: bytes = PNG) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = "Logo"
    msg.set_content("See the logo.")
    msg.add_alternative('<p>Hi <img src="cid:logo@x"> <img src="cid:missing@x"></p>', subtype="html")
    msg.get_payload()[1].add_related(payload, maintype="image", subtype="png", cid="<logo@x>")
    return msg


def test_an_emails_own_inline_image_travels_inside_the_html():
    out = render_message(_with_inline_image())
    assert f'src="data:image/png;base64,{base64.b64encode(PNG).decode()}"' in out["html"]
    assert 'src=""' in out["html"]  # a cid with no part behind it loads nothing
    assert "cid:" not in out["html"]
    assert out["text"].strip() == "See the logo."


def test_the_letters_cid_outside_an_image_address_are_left_alone():
    msg = _with_inline_image()
    html = '<p>Ref cid:12345, acid:rain. <a href="cid:logo@x">logo</a> <img src="cid:logo%40x"></p>'
    msg.get_payload()[1].get_payload()[0].set_content(html, subtype="html")
    out = render_message(msg)["html"]
    assert "Ref cid:12345, acid:rain." in out
    assert 'href="cid:logo@x"' in out
    assert out.count("data:image/png;base64,") == 1  # the one image address, percent-encoded


def test_an_attached_email_is_an_attachment_and_its_body_is_not_shown_as_this_one(tmp_path):
    inner = mail("The original", body="Inner text.", html="<p>INNER HTML</p>")
    outer = EmailMessage()
    outer["Subject"] = "Fwd: The original"
    outer.set_content("See the attached email.")
    outer.add_attachment(inner, filename="original.eml")
    out = render_message(outer)
    assert "See the attached email." in out["html"]
    assert "INNER HTML" not in out["html"]
    assert "Inner text." not in out["text"]
    (listed,) = out["attachments"]
    assert (listed["filename"], listed["content_type"]) == ("original.eml", "message/rfc822")
    assert listed["size"] > 0


def test_an_html_only_email_carrying_another_gives_its_own_text_not_the_attached_ones():
    outer = EmailMessage()
    outer["Subject"] = "Fwd"
    outer.set_content("<p>Mine <b>only</b>.</p>", subtype="html")
    outer.add_attachment(mail("The original", body="Inner text."), filename="original.eml")
    out = render_message(outer)
    assert out["text"] == "Mine only."


def test_text_written_around_an_attachment_is_all_shown():
    msg = EmailMessage()
    msg["Subject"] = "Photos"
    msg.set_content("<p>Before the photo.</p>", subtype="html")
    msg.add_attachment(b"%PDF-fake", maintype="application", subtype="pdf", filename="photo.pdf")
    from email.mime.text import MIMEText

    msg.attach(MIMEText("<p>After the photo.</p>", "html"))
    out = render_message(msg)
    assert "Before the photo." in out["html"] and "After the photo." in out["html"]
    assert out["html"].index("Before") < out["html"].index("After")
    assert "After the photo." in out["text"]
    assert [a["filename"] for a in out["attachments"]] == ["photo.pdf"]


def test_a_bounce_lists_the_original_it_carries_under_its_subject():
    from email.mime.message import MIMEMessage
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    bounce = MIMEMultipart("report")
    bounce["Subject"] = "Undelivered"
    bounce.attach(MIMEText("Your message could not be delivered.", "plain"))
    bounce.attach(MIMEMessage(mail("Lunch on Friday", body="Inner text.")))
    out = render_message(bounce)
    assert "could not be delivered" in out["html"]
    assert "Inner text." not in out["html"] and "Inner text." not in out["text"]
    assert [a["filename"] for a in out["attachments"]] == ["Lunch on Friday.eml"]


def test_an_email_that_is_wholly_a_forwarded_email_shows_that_email():
    from email.mime.message import MIMEMessage

    wrapper = MIMEMessage(mail("Inside", body="The real words."))
    wrapper["Subject"] = "Fwd: Inside"
    assert "The real words." in render_message(wrapper)["html"]


def test_inline_images_past_the_limit_are_left_out(monkeypatch):
    monkeypatch.setattr(render, "_INLINE_LIMIT", 4)
    out = render_message(_with_inline_image())
    assert "data:image" not in out["html"]
    assert "<p>Hi" in out["html"]


def test_a_plain_text_email_is_shown_escaped_with_its_line_breaks():
    out = render_message(mail(body="Line one\n<b>not bold</b>\n"))
    assert "Line one\n&lt;b&gt;not bold&lt;/b&gt;" in out["html"]
    assert out["html"].startswith("<pre")
    assert out["attachments"] == []


def test_attachments_are_listed_with_their_size_and_not_shown_as_the_body():
    out = render_message(mail(body="See attached.", html="<p>See attached.</p>", attachment="report.pdf"))
    assert out["html"].strip() == "<p>See attached.</p>"
    assert out["attachments"] == [
        {"filename": "report.pdf", "content_type": "application/pdf", "size": 9}
    ]


def test_an_email_that_is_wholly_a_forwarded_email_lists_that_emails_attachments():
    from email.mime.message import MIMEMessage

    from coworker.mail.render import attachment_bytes, attachments

    wrapper = MIMEMessage(mail("Inside", body="The real words.", attachment="inner.pdf"))
    wrapper["Subject"] = "Fwd: Inside"
    assert [a["filename"] for a in render_message(wrapper)["attachments"]] == ["inner.pdf"]
    ((name, part),) = attachments(wrapper)  # what saving uses: the same list, the same file
    assert (name, attachment_bytes(part)) == ("inner.pdf", b"%PDF-fake")


def test_every_part_of_an_email_is_either_shown_or_listed():
    from email.mime.application import MIMEApplication
    from email.mime.image import MIMEImage
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("mixed")
    msg["Subject"] = "Odds and ends"
    named = MIMEText("<p>Written as a file, meant as the message.</p>", "html")
    named.add_header("Content-Disposition", "inline", filename="message.html")
    msg.attach(named)
    by_type_only = MIMEApplication(b"%PDF-1", "pdf", name="by-name.pdf")  # no Content-Disposition
    msg.attach(by_type_only)
    capitalised = MIMEApplication(b"%PDF-2", "pdf")
    capitalised.add_header("Content-Disposition", "Attachment", filename="capitalised.pdf")
    msg.attach(capitalised)
    msg.attach(MIMEImage(b"\x89PNG-photo", "png"))  # a photo with no name and no place in the text
    out = render_message(msg)
    assert "meant as the message" in out["html"]
    assert [a["filename"] for a in out["attachments"]] == ["by-name.pdf", "capitalised.pdf", "attachment.png"]
